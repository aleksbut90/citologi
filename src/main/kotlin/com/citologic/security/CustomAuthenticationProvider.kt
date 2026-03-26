package com.citologic.security

import com.citologic.repository.UserRepository
import com.citologic.service.CustomUserDetailsService
import org.springframework.security.authentication.AuthenticationProvider
import org.springframework.security.authentication.BadCredentialsException
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken
import org.springframework.security.core.Authentication
import org.springframework.stereotype.Component

@Component
class CustomAuthenticationProvider(
    private val userDetailsService: CustomUserDetailsService
) : AuthenticationProvider {

    override fun authenticate(authentication: Authentication?): Authentication? {
        if (authentication == null) return null

        val username = authentication.name
        val password = authentication.credentials.toString()

        // Получаем пользователя
        val userDetails = userDetailsService.loadUserByUsername(username)

        // Находим пользователя в БД для получения соли и хэша
        val userDto = UserRepository().findByUsername(username)
            ?: throw BadCredentialsException("Invalid credentials")

        // Проверяем пароль через PBKDF2
        val isValid = userDetailsService.verifyPassword(
            password,
            userDto.passwordSalt,
            userDto.passwordHash
        )

        if (!isValid) {
            // Увеличиваем счетчик неудачных попыток
            userDetailsService.incrementFailedAttempts(userDto.id, userDto.failedAttempts)
            throw BadCredentialsException("Invalid credentials")
        }

        // Сбрасываем счетчик при успешном входе
        userDetailsService.resetFailedAttempts(userDto.id)

        return UsernamePasswordAuthenticationToken(
            userDetails.username,
            userDetails.password,
            userDetails.authorities
        )
    }

    override fun supports(authentication: Class<*>): Boolean {
        return UsernamePasswordAuthenticationToken::class.java.isAssignableFrom(authentication)
    }
}