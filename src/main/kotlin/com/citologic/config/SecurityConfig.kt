package com.citologic.config

import com.citologic.service.CustomUserDetailsService
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.ProviderManager
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.web.SecurityFilterChain

@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val customAuthenticationProvider: CustomAuthenticationProvider
) {

    @Bean
    fun securityFilterChain(http: HttpSecurity): SecurityFilterChain {

        http
            .csrf { it.disable() }
            .authorizeHttpRequests { auth ->
                auth.requestMatchers(
                    "/",                     // ← ВАЖНО!
                    "/login",
                    "/logout",
                    "/error",
                    "/favicon.ico",
                    "/offline-stub.html",

                    // Vaadin internal
                    "/VAADIN/**",
                    "/vaadinServlet/**",
                    "/frontend/**",
                    "/webjars/**",
                    "/themes/**",
                    "/HILLA/**",

                    // Flow client bootstrap
                    "/VAADIN/build/**",
                    "/VAADIN/static/**",
                    "/VAADIN/build/flow-client/**",

                    // Your styles
                    "/styles/**"
                ).permitAll()

                auth.anyRequest().authenticated()
            }
            .authenticationProvider(customAuthenticationProvider)
            .httpBasic { it.disable() }
            .formLogin { it.disable() }
            .logout { logout ->
                logout.logoutSuccessUrl("/login?logout=true")
                logout.invalidateHttpSession(true)
                logout.deleteCookies("JSESSIONID")
            }

        return http.build()
    }

    @Bean
    fun authenticationManager(): AuthenticationManager =
        ProviderManager(customAuthenticationProvider)
}

