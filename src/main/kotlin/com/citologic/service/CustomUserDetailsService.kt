package com.citologic.service

import com.citologic.repository.UserRepository
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.security.core.authority.SimpleGrantedAuthority
import org.springframework.security.core.userdetails.User
import org.springframework.security.core.userdetails.UserDetails
import org.springframework.security.core.userdetails.UserDetailsService
import org.springframework.security.core.userdetails.UsernameNotFoundException
import org.springframework.stereotype.Service
import java.security.SecureRandom
import java.util.*
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

@Service
class CustomUserDetailsService(
    private val userRepository: UserRepository,
) : UserDetailsService {

    companion object {
        private const val PBKDF2_ITERATIONS = 200_000
        private const val KEY_LENGTH = 256
        private const val SALT_LENGTH = 16
    }

    override fun loadUserByUsername(username: String): UserDetails {
        var userDetails: UserDetails? = null
        transaction {
            val userDto = userRepository.findByUsername(username)
                ?: throw UsernameNotFoundException("User not found: $username")

            // Проверяем, заблокирован ли пользователь
            if (userDto.lockUntil != null && userDto.lockUntil > java.time.Instant.now()) {
                throw UsernameNotFoundException("User is locked until ${userDto.lockUntil}")
            }

            // Получаем хэш пароля для Spring Security
            val passwordHash = userDto.passwordHash
                ?: throw UsernameNotFoundException("Password not found for: $username")

            // Для Spring Security создаем пользователя с пустым паролем,
            // так как проверка будет происходить через кастомный AuthenticationProvider
            userDetails = User(
                userDto.login ?: username,
                "", // Пароль проверяется отдельно через verifyPassword
                listOf(SimpleGrantedAuthority("ROLE_${userDto.status ?: "USER"}"))
            )
        }
        return userDetails!!
    }

    /**
     * Генерация соли для PBKDF2
     */
    fun generatePasswordSalt(): String {
        val salt = ByteArray(SALT_LENGTH)
        SecureRandom().nextBytes(salt)
        return Base64.getEncoder().encodeToString(salt)
    }

    /**
     * Хэширование пароля с солью используя PBKDF2 (совместимо со старым Python проектом)
     */
    fun hashPasswordWithSalt(password: String, saltB64: String): String {
        val salt = Base64.getDecoder().decode(saltB64)
        val spec = PBEKeySpec(password.toCharArray(), salt, PBKDF2_ITERATIONS, KEY_LENGTH)
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val hash = factory.generateSecret(spec).encoded
        return Base64.getEncoder().encodeToString(hash)
    }

    /**
     * Проверка пароля (совместимо со старым Python проектом)
     */
    fun verifyPassword(password: String, saltB64: String?, hashB64: String?): Boolean {
        if (saltB64 == null || hashB64 == null) {
            return false
        }
        return try {
            val calculatedHash = hashPasswordWithSalt(password, saltB64)
            // Сравниваем хэши (в Python используется дополнительное SHA256 сравнение)
            val calculatedHashSha = java.security.MessageDigest.getInstance("SHA-256")
                .digest(calculatedHash.encodeToByteArray())
            val storedHashSha = java.security.MessageDigest.getInstance("SHA-256")
                .digest(hashB64.encodeToByteArray())
            calculatedHashSha contentEquals storedHashSha
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Регистрация нового пользователя с хэшированием PBKDF2
     */
    fun registerUser(login: String, rawPassword: String, fioName: String? = null, id: String): Boolean {
        return try {
            // Проверяем, существует ли пользователь
            if (userRepository.findByUsername(login) != null) {
                return false
            }
            
            // Генерируем соль и хэшируем пароль
            val salt = generatePasswordSalt()
            val passwordHash = hashPasswordWithSalt(rawPassword, salt)
            
            // Создаем пользователя
            userRepository.create(
                id = id,
                login = login,
                fioName = fioName,
                passwordHash = passwordHash,
                passwordSalt = salt,
                status = "active"
            )
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Обновление пароля пользователя
     */
    fun updatePassword(userId: String, rawPassword: String): Boolean {
        return try {
            val salt = generatePasswordSalt()
            val passwordHash = hashPasswordWithSalt(rawPassword, salt)
            
            userRepository.update(
                id = userId,
                passwordHash = passwordHash,
                passwordSalt = salt,
                password = null // Очищаем старый пароль в простом формате
            )
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Увеличение счетчика неудачных попыток входа
     */
    fun incrementFailedAttempts(userId: String, currentAttempts: Int, lockTimeMinutes: Int = 30): Boolean {
        val newAttempts = currentAttempts + 1
        val lockUntil = if (newAttempts >= 5) {
            java.time.Instant.now().plusSeconds((lockTimeMinutes * 60).toLong())
        } else {
            null
        }
        return userRepository.updateFailedAttempts(userId, newAttempts, lockUntil)
    }

    /**
     * Сброс счетчика неудачных попыток после успешного входа
     */
    fun resetFailedAttempts(userId: String): Boolean {
        return userRepository.updateFailedAttempts(userId, 0, null)
    }
}
