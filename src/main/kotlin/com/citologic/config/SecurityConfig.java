package com.citologic.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.CsrfConfigurer;
import org.springframework.security.config.annotation.web.configurers.HeadersConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;

import static org.springframework.security.web.util.matcher.RegexRequestMatcher.regexMatcher;

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
        return http
                .headers(httpSecurityHeadersConfigurer ->
                        httpSecurityHeadersConfigurer.frameOptions(
                                HeadersConfigurer.FrameOptionsConfig::disable
                        )
                )
                .csrf(CsrfConfigurer::disable)
                .requestCache(cache -> {
                            HttpSessionRequestCache requestCache = new HttpSessionRequestCache();
                            requestCache.setMatchingRequestParameterName("continue");
                            cache.requestCache(requestCache);
                        }
                )
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                regexMatcher("/VAADIN/.*"),
                                regexMatcher("/frontend/.*"),
                                regexMatcher("/webjars/.*"),
                                regexMatcher("/icons/.*"),
                                regexMatcher("/images/.*"),
                                regexMatcher("/styles/.*"),
                                regexMatcher("/manifest.webmanifest"),
                                regexMatcher("/sw.js"),
                                regexMatcher("/offline.html"),
                                regexMatcher("/sw-runtime-resources-precache.js"),
                                regexMatcher("/favicon.ico"),
                                regexMatcher("/robots.txt"),
                                regexMatcher("/h2-console/.*"),
                                regexMatcher("/login$"),
                                regexMatcher("/error/.*"),
                                regexMatcher("/logout.*")
                        ).permitAll()
                        .anyRequest().authenticated()
                )
                .formLogin(form -> form
                        .loginPage("/login")
                        .loginProcessingUrl("/login")
                        .defaultSuccessUrl("/", true)
                        .permitAll())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/login?logout")
                        .invalidateHttpSession(true)
                        .deleteCookies("JSESSIONID")
                        .permitAll())
                .build();
    }
}
