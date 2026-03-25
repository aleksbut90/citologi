package com.citologic.service

import com.citologic.repository.UserRepository
import org.springframework.security.core.authority.SimpleGrantedAuthority
import org.springframework.security.core.userdetails.User
import org.springframework.security.core.userdetails.UserDetails
import org.springframework.security.core.userdetails.UserDetailsService
import org.springframework.security.core.userdetails.UsernameNotFoundException
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class CustomUserDetailsService(
    private val userRepository: UserRepository,
    private val passwordEncoder: BCryptPasswordEncoder
) : UserDetailsService {

    @Transactional(readOnly = true)
    override fun loadUserByUsername(username: String): UserDetails {
        val userDto = userRepository.findByUsername(username)
            ?: throw UsernameNotFoundException("User not found: $username")

        val passwordHash = userRepository.findPasswordHashByUsername(username)
            ?: throw UsernameNotFoundException("Password not found for: $username")

        return User(
            userDto.username,
            passwordHash,
            listOf(SimpleGrantedAuthority("ROLE_${userDto.role}"))
        )
    }

    fun registerUser(username: String, rawPassword: String) {
        if (userRepository.findByUsername(username) != null) {
            throw IllegalArgumentException("User already exists")
        }
        val hash = passwordEncoder.encode(rawPassword)
        userRepository.create(username, hash)
    }
}
