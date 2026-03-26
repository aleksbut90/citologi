package com.citologic.config;

import com.citologic.security.CustomAuthenticationProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final CustomAuthenticationProvider authProvider;

    public SecurityConfig(CustomAuthenticationProvider authProvider) {
        this.authProvider = authProvider;
    }

    @Bean
    public AuthenticationManager authenticationManager() {
        return new ProviderManager(authProvider);
    }

    @Bean
    @Order(1)
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        // Настройка заголовков
        http.headers(headers -> headers.frameOptions(frame -> frame.disable()));

        // Отключаем CSRF
        http.csrf(csrf -> csrf.disable());

        // Настройка кэша запросов
        http.requestCache(cache -> cache.requestCache(new HttpSessionRequestCache()));

        // Настройка авторизации
        http.authorizeHttpRequests(auth -> auth
            // Ресурсы Vaadin и статика
            .requestMatchers(new RegexRequestMatcher("/VAADIN/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/frontend/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/webjars/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/icons/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/images/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/styles/.*", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/manifest.webmanifest", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/sw.js", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/offline.html", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/sw-runtime-resources-precache.js", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/favicon.ico", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/robots.txt", null)).permitAll()
            
            // Страницы логина, logout, error
            .requestMatchers(new RegexRequestMatcher("/login", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/logout", null)).permitAll()
            .requestMatchers(new RegexRequestMatcher("/error", null)).permitAll()
            
            // Всё остальное требует авторизации
            .anyRequest().authenticated()
        );

        // Настройка формы входа
        http.formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .defaultSuccessUrl("/", true)
            .permitAll()
        );

        // Настройка выхода
        http.logout(logout -> logout
            .logoutUrl("/logout")
            .logoutSuccessUrl("/login?logout")
            .invalidateHttpSession(true)
            .deleteCookies("JSESSIONID")
            .permitAll()
        );

        return http.build();
    }
}
