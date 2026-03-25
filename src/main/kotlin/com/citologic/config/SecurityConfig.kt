package com.citologic.config

import com.citologic.service.CustomUserDetailsService
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
import org.springframework.security.crypto.password.PasswordEncoder
import com.vaadin.flow.spring.security.VaadinWebSecurity

@Configuration
class SecurityConfig(
    private val userDetailsService: CustomUserDetailsService
) : VaadinWebSecurity() {

    @Bean
    fun passwordEncoder(): PasswordEncoder = BCryptPasswordEncoder()

    @Bean
    fun authenticationManager(authConfig: AuthenticationConfiguration): AuthenticationManager {
        return authConfig.authenticationManager
    }

    override fun configure(http: HttpSecurity) {
        super.configure(http)
        
        http
            .authorizeHttpRequests { authorize ->
                authorize
                    .requestMatchers("/login").permitAll()
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
