package com.citologic.config

import com.citologic.service.CustomUserDetailsService
import com.vaadin.flow.spring.security.VaadinWebSecurity
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.ProviderManager
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.web.SecurityFilterChain
import org.springframework.security.web.util.matcher.AntPathRequestMatcher

@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val customAuthenticationProvider: CustomAuthenticationProvider
) : VaadinWebSecurity() {

    override fun configure(http: HttpSecurity) {
        http
            .csrf { it.disable() }
            .authorizeHttpRequests { auth ->
                auth.requestMatchers(
                    "/login",
                    "/logout",
                    "/error",
                    "/favicon.ico",
                    "/offline-stub.html"
                ).permitAll()

                // Все остальные запросы требуют аутентификации
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
    }

    @Bean
    fun authenticationManager(): AuthenticationManager =
        ProviderManager(customAuthenticationProvider)
}

