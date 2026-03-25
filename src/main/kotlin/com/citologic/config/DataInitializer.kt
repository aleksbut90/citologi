package com.citologic.config

import com.citologic.service.CustomUserDetailsService
import org.springframework.boot.CommandLineRunner
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.crypto.password.PasswordEncoder

@Configuration
class DataInitializer(
    private val userDetailsService: CustomUserDetailsService,
    private val passwordEncoder: PasswordEncoder
) {

    @Bean
    fun initUsers(): CommandLineRunner = CommandLineRunner {
        // Создаем тестового админа, если его нет
        try {
            userDetailsService.registerUser("admin", "admin123")
            println(">>> User 'admin' created with password 'admin123'")
        } catch (e: Exception) {
            println(">>> User 'admin' already exists or error: ${e.message}")
        }
        
        try {
            userDetailsService.registerUser("user", "user123")
            println(">>> User 'user' created with password 'user123'")
        } catch (e: Exception) {
            println(">>> User 'user' already exists or error: ${e.message}")
        }
    }
}
