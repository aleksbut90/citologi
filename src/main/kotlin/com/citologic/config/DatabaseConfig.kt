package com.citologic.config

import org.jetbrains.exposed.sql.Database
import org.jetbrains.exposed.sql.SchemaUtils
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import com.citologic.model.*
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

        // Создаем таблицы только если они не существуют (используем существующую схему БД)
        transaction {
            // Основные таблицы
            SchemaUtils.createMissingTablesAndColumns(
                UsersTable,
                UserSessions,
                Patients,
                Materials,
                Studies,
                Otdel,
                Physicians,
                SampleTypes,
                Bethesda,
                CodeCytology,
                LabResults,
                Mkb,
                Lpu,
                Raion,
                Service,
                ServiceTypes,
                StudyCharacter,
                Comments,
                Docnaprav,
                Gistolog,
                Loc,
                Organ,
                Profosmotr,
                Ecp45mis,
                Swrat
            )
        }
    }
}
