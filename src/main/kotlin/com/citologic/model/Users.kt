package com.citologic.model

import org.jetbrains.exposed.sql.Table
import org.jetbrains.exposed.sql.javatime.timestamp
import java.time.Instant

// Обновленная модель Users для работы с существующей схемой БД
object UsersTable : Table("\"user\"") {
    val id = varchar("id", 255)
    val fioName = varchar("fio_name", 255).nullable()
    val login = varchar("login", 255).nullable()
    val password = varchar("password", 255).nullable()
    val status = varchar("status", 255).nullable()
    val sessionId = integer("sessionid").nullable()
    val passwordHash = text("password_hash").nullable()
    val passwordSalt = text("password_salt").nullable()
    val failedAttempts = integer("failed_attempts").default(0)
    val lockUntil = timestamp("lock_until").nullable()

    override val primaryKey = PrimaryKey(id)
}

data class UserDto(
    val id: String,
    val fioName: String?,
    val login: String?,
    val status: String?,
    val passwordHash: String?,
    val passwordSalt: String?,
    val password: String?,
    val failedAttempts: Int,
    val lockUntil: Instant?
)
