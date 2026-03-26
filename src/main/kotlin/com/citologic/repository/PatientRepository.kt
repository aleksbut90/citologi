package com.citologic.repository

import com.citologic.model.*
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.SqlExpressionBuilder.eq
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.stereotype.Repository
import java.time.LocalDate

@Repository
class PatientRepository {

    fun findAll(): List<PatientDto> = transaction {
        Patients.selectAll()
            .map { row ->
                PatientDto(
                    id = row[Patients.id],
                    fullName = row[Patients.fullName],
                    snils = row[Patients.snils],
                    districtId = row[Patients.districtId],
                    address = row[Patients.address],
                    insurancePolicyNumber = row[Patients.insurancePolicyNumber],
                    ambulatoryCardNumber = row[Patients.ambulatoryCardNumber],
                    isEmployed = row[Patients.isEmployed],
                    isDismissed = row[Patients.isDismissed],
                    dismissalDate = row[Patients.dismissalDate],
                    birthdate = row[Patients.birthdate]
                )
            }
    }

    fun findById(id: Int): PatientDto? = transaction {
        Patients.select { Patients.id eq id }
            .map { row ->
                PatientDto(
                    id = row[Patients.id],
                    fullName = row[Patients.fullName],
                    snils = row[Patients.snils],
                    districtId = row[Patients.districtId],
                    address = row[Patients.address],
                    insurancePolicyNumber = row[Patients.insurancePolicyNumber],
                    ambulatoryCardNumber = row[Patients.ambulatoryCardNumber],
                    isEmployed = row[Patients.isEmployed],
                    isDismissed = row[Patients.isDismissed],
                    dismissalDate = row[Patients.dismissalDate],
                    birthdate = row[Patients.birthdate]
                )
            }
            .singleOrNull()
    }

    fun findByFio(query: String): List<PatientDto> = transaction {
        if (query.isBlank()) {
            emptyList()
        } else {
            Patients.select {
                Patients.fullName.like("%$query%")
            }
                .map { row ->
                    PatientDto(
                        id = row[Patients.id],
                        fullName = row[Patients.fullName],
                        snils = row[Patients.snils],
                        districtId = row[Patients.districtId],
                        address = row[Patients.address],
                        insurancePolicyNumber = row[Patients.insurancePolicyNumber],
                        ambulatoryCardNumber = row[Patients.ambulatoryCardNumber],
                        isEmployed = row[Patients.isEmployed],
                        isDismissed = row[Patients.isDismissed],
                        dismissalDate = row[Patients.dismissalDate],
                        birthdate = row[Patients.birthdate]
                    )
                }
        }
    }

    fun findAllOrganizations(): List<String> = transaction {
        Lpu.selectAll()
            .map { it[Lpu.name] }
            .distinct()
    }

    fun findAllDepartments(): List<String> = transaction {
        Otdel.selectAll()
            .map { row -> row[Otdel.name].orEmpty() }
            .filter { it.isNotEmpty() }
            .distinct()
    }

    fun create(
        fullName: String,
        snils: String? = null,
        districtId: String? = null,
        address: String? = null,
        insurancePolicyNumber: String? = null,
        ambulatoryCardNumber: String? = null,
        isEmployed: Boolean? = null,
        isDismissed: Boolean = false,
        dismissalDate: LocalDate? = null,
        birthdate: LocalDate? = null
    ): PatientDto = transaction {
        val id = Patients.insert {
            it[Patients.fullName] = fullName
            it[Patients.snils] = snils
            it[Patients.districtId] = districtId
            it[Patients.address] = address
            it[Patients.insurancePolicyNumber] = insurancePolicyNumber
            it[Patients.ambulatoryCardNumber] = ambulatoryCardNumber
            it[Patients.isEmployed] = isEmployed
            it[Patients.isDismissed] = isDismissed
            dismissalDate?.let { date -> it[Patients.dismissalDate] = date }
            birthdate?.let { date -> it[Patients.birthdate] = date }
        } get Patients.id

        PatientDto(
            id = id,
            fullName = fullName,
            snils = snils,
            districtId = districtId,
            address = address,
            insurancePolicyNumber = insurancePolicyNumber,
            ambulatoryCardNumber = ambulatoryCardNumber,
            isEmployed = isEmployed,
            isDismissed = isDismissed,
            dismissalDate = dismissalDate,
            birthdate = birthdate
        )
    }

    fun update(
        id: Int,
        fullName: String? = null,
        snils: String? = null,
        districtId: String? = null,
        address: String? = null,
        insurancePolicyNumber: String? = null,
        ambulatoryCardNumber: String? = null,
        isEmployed: Boolean? = null,
        isDismissed: Boolean? = null,
        dismissalDate: LocalDate? = null,
        birthdate: LocalDate? = null
    ): Boolean = transaction {
        Patients.update({ Patients.id eq id }) { patientUpdate ->
            fullName?.let { patientUpdate[Patients.fullName] = fullName }
            snils?.let { patientUpdate[Patients.snils] = snils }
            districtId?.let { patientUpdate[Patients.districtId] = districtId }
            address?.let { patientUpdate[Patients.address] = address }
            insurancePolicyNumber?.let { patientUpdate[Patients.insurancePolicyNumber] = insurancePolicyNumber }
            ambulatoryCardNumber?.let { patientUpdate[Patients.ambulatoryCardNumber] = ambulatoryCardNumber }
            isEmployed?.let { patientUpdate[Patients.isEmployed] = isEmployed }
            isDismissed?.let { patientUpdate[Patients.isDismissed] = isDismissed }
            dismissalDate?.let { patientUpdate[Patients.dismissalDate] = dismissalDate }
            birthdate?.let { patientUpdate[Patients.birthdate] = birthdate }
        } > 0
    }

    fun delete(id: Int): Boolean = transaction {
        Patients.deleteWhere { Patients.id eq id } > 0
    }
}

data class PatientDto(
    val id: Int,
    val fullName: String,
    val snils: String?,
    val districtId: String?,
    val address: String?,
    val insurancePolicyNumber: String?,
    val ambulatoryCardNumber: String?,
    val isEmployed: Boolean?,
    val isDismissed: Boolean,
    val dismissalDate: LocalDate?,
    val birthdate: LocalDate?
) {
    val lastName: String get() = fullName.split(" ").getOrElse(0) { "" }
    val firstName: String get() = fullName.split(" ").getOrElse(1) { "" }
    val middleName: String get() = fullName.split(" ").getOrElse(2) { "" }
}
