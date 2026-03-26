package com.citologic.security

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.ProviderManager
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer
import org.springframework.security.web.SecurityFilterChain

@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val authProvider: CustomAuthenticationProvider
) {

    @Bean
    fun authenticationManager(): AuthenticationManager =
        ProviderManager(authProvider)

    @Bean
    fun filterChain(http: HttpSecurity): SecurityFilterChain {

        return http
            .csrf { it.disable() }
            .headers { it.frameOptions { f -> f.disable() } }
            .authorizeHttpRequests { auth ->
                auth
                    // Vaadin UI — ВСЁ permitAll
                    .requestMatchers(
                        "/",
                        "/login",
                        "/login/**",
                        "/logout",
                        "/error",
                        "/favicon.ico",
                        "/offline.html",
                        "/VAADIN/**",
                        "/frontend/**",
                        "/webjars/**",
                        "/icons/**",
                        "/images/**",
                        "/styles/**",
                        "/manifest.webmanifest",
                        "/sw.js",
                        "/sw-runtime-resources-precache.js",
                        "/robots.txt"
                    ).permitAll()

                    // Только backend API защищаем
                    .requestMatchers(
                        "/consult/**",
                        "/soap/**",
                        "/api/**"
                    ).authenticated()

                    // Всё остальное — UI, отдаём Vaadin
                    .anyRequest().permitAll()
            }
            .formLogin { it.disable() }
            .httpBasic { it.disable() }
            .build()
    }
}
