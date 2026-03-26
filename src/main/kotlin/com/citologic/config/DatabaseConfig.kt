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
        // Добавляем таймауты для предотвращения зависания при проблемах с сетью
        val connectionUrl = if (dbUrl.contains("?")) {
            "$dbUrl&connectTimeout=10&socketTimeout=30"
        } else {
            "$dbUrl?connectTimeout=10&socketTimeout=30"
        }
        
        Database.connect(
            url = connectionUrl, 
            driver = driverClass, 
            user = dbUser, 
            password = dbPassword,
            setupConnection = { connection ->
                // Дополнительные настройки соединения
                connection.networkTimeout = java.util.concurrent.Executors.newSingleThreadExecutor()
                connection.holdability = java.sql.Connection.HOLD_CURSORS_OVER_COMMIT
            }
        )
    }
}
