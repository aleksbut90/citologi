package com.citologic.config

import com.citologic.service.CustomUserDetailsService
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.dao.DaoAuthenticationProvider
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.crypto.password.PasswordEncoder
import org.springframework.security.web.SecurityFilterChain
import com.vaadin.flow.spring.security.VaadinWebSecurity

@Configuration
class SecurityConfig(
    private val userDetailsService: CustomUserDetailsService
) : VaadinWebSecurity() {

    @Bean
    fun passwordEncoder(): PasswordEncoder = PasswordEncoder { 
        // Этот PasswordEncoder не используется для кодирования, только для проверки
        throw UnsupportedOperationException("Use CustomUserDetailsService.verifyPassword instead")
    }

    @Bean
    fun authenticationProvider(): DaoAuthenticationProvider {
        val provider = DaoAuthenticationProvider()
        provider.setUserDetailsService(userDetailsService)
        provider.setPasswordEncoder(passwordEncoder())
        return provider
    }

    @Bean
    fun authenticationManager(authConfig: AuthenticationConfiguration): AuthenticationManager {
        return authConfig.authenticationManager
    }

    override fun configure(http: HttpSecurity) {
        super.configure(http)
        
        http
            .authorizeHttpRequests { authorize ->
                authorize
                    .requestMatchers("/login", "/api/login").permitAll()
                    .requestMatchers("/public/**").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated()
            }
            .formLogin { form ->
                form
                    .loginPage("/login")
                    .permitAll()
                    .defaultSuccessUrl("/", true)
                    .failureUrl("/login?error")
            }
            .logout { logout ->
                logout.logoutSuccessUrl("/login?logout")
            }
    }
}
