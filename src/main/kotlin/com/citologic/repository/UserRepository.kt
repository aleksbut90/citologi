package com.citologic.repository

import com.citologic.model.UsersTable
import com.citologic.model.UserDto
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.stereotype.Repository
import java.time.Instant

@Repository
class UserRepository {

    fun findByUsername(username: String): UserDto? = transaction {
        UsersTable.select { UsersTable.login eq username }
            .map { row ->
                UserDto(
                    id = row[UsersTable.id],
                    fioName = row[UsersTable.fioName],
                    login = row[UsersTable.login],
                    status = row[UsersTable.status],
                    passwordHash = row[UsersTable.passwordHash],
                    passwordSalt = row[UsersTable.passwordSalt],
                    password = row[UsersTable.password],
                    failedAttempts = row[UsersTable.failedAttempts],
                    lockUntil = row[UsersTable.lockUntil]
                )
            }
            .singleOrNull()
    }

    fun findById(id: String): UserDto? = transaction {
        UsersTable.select { UsersTable.id eq id }
            .map { row ->
                UserDto(
                    id = row[UsersTable.id],
                    fioName = row[UsersTable.fioName],
                    login = row[UsersTable.login],
                    status = row[UsersTable.status],
                    passwordHash = row[UsersTable.passwordHash],
                    passwordSalt = row[UsersTable.passwordSalt],
                    password = row[UsersTable.password],
                    failedAttempts = row[UsersTable.failedAttempts],
                    lockUntil = row[UsersTable.lockUntil]
                )
            }
            .singleOrNull()
    }

    fun findAll(): List<UserDto> = transaction {
        UsersTable.selectAll()
            .map { row ->
                UserDto(
                    id = row[UsersTable.id],
                    fioName = row[UsersTable.fioName],
                    login = row[UsersTable.login],
                    status = row[UsersTable.status],
                    passwordHash = row[UsersTable.passwordHash],
                    passwordSalt = row[UsersTable.passwordSalt],
                    password = row[UsersTable.password],
                    failedAttempts = row[UsersTable.failedAttempts],
                    lockUntil = row[UsersTable.lockUntil]
                )
            }
    }

    fun create(
        id: String,
        login: String,
        fioName: String? = null,
        passwordHash: String? = null,
        passwordSalt: String? = null,
        password: String? = null,
        status: String? = "active"
    ): UserDto = transaction {
        UsersTable.insert {
            it[UsersTable.id] = id
            it[UsersTable.login] = login
            it[UsersTable.fioName] = fioName
            it[UsersTable.passwordHash] = passwordHash
            it[UsersTable.passwordSalt] = passwordSalt
            it[UsersTable.password] = password
            it[UsersTable.status] = status
        }

        UserDto(
            id = id,
            fioName = fioName,
            login = login,
            status = status,
            passwordHash = passwordHash,
            passwordSalt = passwordSalt,
            password = password,
            failedAttempts = 0,
            lockUntil = null
        )
    }

    fun update(
        id: String,
        login: String? = null,
        fioName: String? = null,
        passwordHash: String? = null,
        passwordSalt: String? = null,
        password: String? = null,
        status: String? = null
    ): Boolean = transaction {
        UsersTable.update({ UsersTable.id eq id }) { userUpdate ->
            login?.let { userUpdate[UsersTable.login] = login }
            fioName?.let { userUpdate[UsersTable.fioName] = fioName }
            passwordHash?.let { userUpdate[UsersTable.passwordHash] = passwordHash }
            passwordSalt?.let { userUpdate[UsersTable.passwordSalt] = passwordSalt }
            password?.let { userUpdate[UsersTable.password] = password }
            status?.let { userUpdate[UsersTable.status] = status }
        } > 0
    }

    fun delete(id: String): Boolean = transaction {
        UsersTable.deleteWhere { UsersTable.id eq id } > 0
    }

    fun updateFailedAttempts(id: String, failedAttempts: Int, lockUntil: Instant?): Boolean = transaction {
        UsersTable.update({ UsersTable.id eq id }) {
            it[UsersTable.failedAttempts] = failedAttempts
            it[UsersTable.lockUntil] = lockUntil
        } > 0
    }

    fun searchUsers(query: String): List<UserDto> = transaction {
        UsersTable.select {
            UsersTable.login.like("%$query%") or UsersTable.fioName.like("%$query%")
        }
            .map { row ->
                UserDto(
                    id = row[UsersTable.id],
                    fioName = row[UsersTable.fioName],
                    login = row[UsersTable.login],
                    status = row[UsersTable.status],
                    passwordHash = row[UsersTable.passwordHash],
                    passwordSalt = row[UsersTable.passwordSalt],
                    password = row[UsersTable.password],
                    failedAttempts = row[UsersTable.failedAttempts],
                    lockUntil = row[UsersTable.lockUntil]
                )
            }
    }
}
