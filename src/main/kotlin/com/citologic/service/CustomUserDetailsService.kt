package com.citologic.service

import com.citologic.repository.UserRepository
import org.jetbrains.exposed.sql.transaction
import org.springframework.security.core.authority.SimpleGrantedAuthority
import org.springframework.security.core.userdetails.User
import org.springframework.security.core.userdetails.UserDetails
import org.springframework.security.core.userdetails.UserDetailsService
import org.springframework.security.core.userdetails.UsernameNotFoundException
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder
import org.springframework.stereotype.Service

@Service
class CustomUserDetailsService(
    private val userRepository: UserRepository,
    private val passwordEncoder: BCryptPasswordEncoder
) : UserDetailsService {

    override fun loadUserByUsername(username: String): UserDetails {
        var userDetails: UserDetails? = null
        transaction {
            val userDto = userRepository.findByUsername(username)
                ?: throw UsernameNotFoundException("User not found: $username")

            val passwordHash = userRepository.findPasswordHashByUsername(username)
                ?: throw UsernameNotFoundException("Password not found for: $username")

            userDetails = User(
                userDto.username,
                passwordHash,
                listOf(SimpleGrantedAuthority("ROLE_${userDto.role}"))
            )
        }
        return userDetails!!
    }

    fun registerUser(username: String, rawPassword: String) {
        transaction {
            if (userRepository.findByUsername(username) != null) {
                throw IllegalArgumentException("User already exists")
            }
            val hash = passwordEncoder.encode(rawPassword)
            userRepository.create(username, hash)
        }
    }
}
