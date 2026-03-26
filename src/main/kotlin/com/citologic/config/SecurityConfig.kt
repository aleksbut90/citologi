package com.citologic.config

import com.citologic.service.CustomAuthenticationProvider
import com.citologic.ui.LoginView
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.annotation.Order
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.ProviderManager
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.web.SecurityFilterChain
import org.springframework.security.web.util.matcher.AntPathRequestMatcher
import org.springframework.security.web.util.matcher.RegexRequestMatcher

@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val customAuthenticationProvider: CustomAuthenticationProvider
) {

    @Bean
    fun authenticationManager(): AuthenticationManager =
        ProviderManager(customAuthenticationProvider)

    @Bean
    @Order(1)
    fun vaadinFilterChain(http: HttpSecurity): SecurityFilterChain {
        return http
            .csrf { it.disable() }
            .authorizeHttpRequests { auth ->
                auth.requestMatchers { request ->
                    // Разрешаем внутренние запросы Vaadin
                    request.requestURI.startsWith("/VAADIN/") ||
                    request.requestURI.startsWith("/HILLA/") ||
                    request.requestURI == "/favicon.ico" ||
                    request.requestURI == "/manifest.webmanifest" ||
                    request.requestURI == "/sw.js" ||
                    request.requestURI == "/offline.html" ||
                    request.requestURI.startsWith("/icons/") ||
                    request.requestURI.startsWith("/images/") ||
                    request.requestURI.startsWith("/styles/") ||
                    request.requestURI == "/sw-runtime-resources-precache.js" ||
                    request.requestURI.startsWith("/error/")
                }.permitAll()
                .requestMatchers(AntPathRequestMatcher("/login")).permitAll()
                .requestMatchers(AntPathRequestMatcher("/logout")).permitAll()
                .anyRequest().authenticated()
            }
            .formLogin { form ->
                form.loginPage("/login")
                    .loginProcessingUrl("/login")
                    .permitAll()
            }
            .logout { logout ->
                logout.logoutSuccessUrl("/login?logout=true")
                logout.invalidateHttpSession(true)
                logout.deleteCookies("JSESSIONID")
            }
            .build()
    }

    @Bean
    @Order(2)
    fun filterChain(http: HttpSecurity): SecurityFilterChain {
        return http
            .csrf { it.disable() }
            .authorizeHttpRequests { auth ->
                auth.anyRequest().authenticated()
            }
            .build()
    }
}

