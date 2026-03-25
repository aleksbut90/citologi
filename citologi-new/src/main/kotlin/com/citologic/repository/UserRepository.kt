package com.citologic.repository

import com.citologic.model.Users
import com.citologic.model.UserDto
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.stereotype.Repository

@Repository
class UserRepository {

    fun findByUsername(username: String): UserDto? = transaction {
        Users.select { Users.username eq username }
            .map { row -> UserDto(row[Users.id], row[Users.username], row[Users.role]) }
            .singleOrNull()
    }

    fun findPasswordHashByUsername(username: String): String? = transaction {
        Users.select { Users.username eq username }
            .map { it[Users.passwordHash] }
            .singleOrNull()
    }

    fun create(username: String, passwordHash: String, role: String = "USER"): UserDto = transaction {
        val id = Users.insert {
            it[Users.username] = username
            it[Users.passwordHash] = passwordHash
            it[Users.role] = role
        } get Users.id

        UserDto(id, username, role)
    }
}
