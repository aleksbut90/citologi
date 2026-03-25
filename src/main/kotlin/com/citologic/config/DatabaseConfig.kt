package com.citologic.config

import org.jetbrains.exposed.sql.Database
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import jakarta.annotation.PostConstruct

@Configuration
class DatabaseConfig(
    @Value("\${spring.datasource.url}") private val dbUrl: String,
    @Value("\${spring.datasource.username}") private val dbUser: String,
    @Value("\${spring.datasource.password}") private val dbPassword: String,
    @Value("\${spring.datasource.driver-class-name}") private val driverClass: String
) {

    @PostConstruct
    fun init() {
        Database.connect(url = dbUrl, driver = driverClass, user = dbUser, password = dbPassword)
    }
}
