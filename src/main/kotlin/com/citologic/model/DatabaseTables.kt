package com.citologic.model

import org.jetbrains.exposed.sql.Table
import org.jetbrains.exposed.sql.javatime.date
import org.jetbrains.exposed.sql.javatime.timestamp
import java.time.LocalDate
import java.time.Instant

// Таблица user - пользователи системы
object Users : Table("\"user\"") {
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

// Таблица user_sessions - сессии пользователей
object UserSessions : Table("user_sessions") {
    val id = integer("id").autoIncrement()
    val userId = varchar("user_id", 255)
    val sessionHash = varchar("session_hash", 255)
    val createdAt = timestamp("created_at").defaultExpression(org.jetbrains.exposed.sql.CurrentDateTime())
    val expiresAt = timestamp("expires_at")
    val isActive = bool("is_active").default(true)
    val sessionId = integer("session_id").nullable()
    val ipAddress = varchar("ip_address", 255).nullable()
    val userAgent = varchar("user_agent", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица patients - пациенты
object Patients : Table("patients") {
    val id = integer("id").autoIncrement()
    val fullName = varchar("full_name", 255)
    val snils = varchar("snils", 14).nullable()
    val districtId = text("district_id").nullable()
    val address = text("address").nullable()
    val insurancePolicyNumber = varchar("insurance_policy_number", 25).nullable()
    val ambulatoryCardNumber = varchar("ambulatory_card_number", 255).nullable()
    val isEmployed = bool("is_employed").nullable()
    val isDismissed = bool("is_dismissed").default(false)
    val dismissalDate = date("dismissal_date").nullable()
    val birthdate = date("birthdate").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица materials - материалы исследований
object Materials : Table("materials") {
    val id = integer("id").autoIncrement()
    val patientId = integer("patient_id")
    val directionNumber = varchar("direction_number", 255).nullable()
    val medicalOrganizationId = varchar("medical_organization_id", 255).nullable()
    val receiptDate = date("receipt_date").nullable()
    val slidesCount = integer("slides_count").nullable()
    val departmentId = varchar("department_id", 32).nullable()
    val referringDoctorId = integer("referring_doctor_id").nullable()
    val researchTypeId = integer("research_type_id").nullable()
    val clinicalDiagnosisId = text("clinical_diagnosis_id").nullable()
    val localizationId = integer("localization_id").nullable()
    val materialTypeId = varchar("material_type_id", 255).nullable()
    val histologicallyConfirmed = bool("histologically_confirmed").nullable()
    val conclusionMatched = bool("conclusion_matched").nullable()
    val isReviewed = varchar("is_reviewed", 255).nullable()
    val studiesId = varchar("studies_id", 255).nullable()
    val gisologComment = varchar("gisolog_comment", 255).nullable()
    val subdepartmentId = varchar("subdepartment_id").nullable()
    val ciphersId = varchar("ciphers_id", 255).nullable()
    val version = integer("version").default(0)
    val lockedByUserId = varchar("locked_by_user_id", 255).nullable()
    val lockedAt = timestamp("locked_at").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица studies - исследования
object Studies : Table("studies") {
    val id = integer("id").autoIncrement()
    val studyDate = date("study_date")
    val doctorId = varchar("doctor_id", 255).nullable()
    val labTechnicianId = varchar("lab_technician_id", 255).nullable()
    val isReviewed = bool("is_reviewed").nullable()
    val znoDno = varchar("zno_dno", 255).nullable()
    val serviceId = integer("service_id").nullable()
    val urgencyId = integer("urgency_id").nullable()
    val studyTypeId = integer("study_type_id").nullable()
    val isFluid = bool("is_fluid").nullable()
    val slidesCount = integer("slides_count").nullable()
    val transferredToDoctor = integer("transferred_to_doctor").nullable()
    val bethesdaTermId = varchar("bethesda_term_id", 255).nullable()
    val pathologiesCount = integer("pathologies_count").nullable()
    val comment = text("comment").nullable()
    val patientId = integer("patient_id").nullable()
    val barcode = varchar("barcode", 64).nullable()
    val materialId = integer("material_id").nullable()
    val conclusionText = text("conclusion_text").nullable()
    val version = integer("version").default(0)
    val lockedByUserId = varchar("locked_by_user_id", 255).nullable()
    val lockedAt = timestamp("locked_at").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица otdel - отделения/подразделения
object Otdel : Table("otdel") {
    val id = varchar("id", 32)
    val department = varchar("department", 255).nullable()
    val podotdelId = varchar("podotdel_id").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица physicians - врачи (справочник)
object Physicians : Table("physicians") {
    val id = integer("id").autoIncrement()
    val fullName = varchar("full_name", 255)
    val role = varchar("role", 50)
    val createdAt = timestamp("created_at").defaultExpression(org.jetbrains.exposed.sql.CurrentDateTime())

    override val primaryKey = PrimaryKey(id)
}

// Таблица sample_types - типы образцов
object SampleTypes : Table("sample_types") {
    val code = integer("code")
    val name = text("name")

    override val primaryKey = PrimaryKey(code)
}

// Таблица betesda - термины Bethesda
object Bethesda : Table("betesda") {
    val uniqueId = integer("unique_id")
    val fullName = text("full_name")
    val abbreviation = text("abbreviation").nullable()

    override val primaryKey = PrimaryKey(uniqueId)
}

// Таблица code_cytology - коды цитологии
object CodeCytology : Table("code_cytology") {
    val id = integer("id").autoIncrement()
    val codeSi = varchar("code_si", 255).nullable()
    val nameCodeSi = varchar("name_code_si", 255).nullable()
    val tipId = integer("tip_id").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица lab_results - результаты лабораторных исследований
object LabResults : Table("lab_results") {
    val id = integer("id").autoIncrement()
    val nompat = integer("nompat")
    val lpuprof = integer("lpuprof")
    val datprof = date("datprof")
    val mazkov = integer("mazkov")
    val issled = integer("issled")
    val vratprof = integer("vratprof")
    val peredan = integer("peredan")
    val laborant = varchar("laborant", 50)
    val nilmlaborant = varchar("nilmlaborant", 50)
    val hpv = integer("hpv")
    val lsilHpv = integer("lsil_hpv")
    val nilm = integer("nilm")
    val ascus = integer("ascus")
    val cini = integer("cini")
    val cinii = integer("cinii")
    val ciniii = integer("ciniii")
    val podcr = integer("podcr")
    val cr = integer("cr")
    val ascH = integer("asc_h")
    val agc = integer("agc")
    val podopuh = integer("podopuh")
    val adenocarc = integer("adenocarc")
    val other = integer("other")
    val tipIsledov = integer("tip_isledov").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица mkb - МКБ коды
object Mkb : Table("mkb") {
    val id = integer("id").autoIncrement()
    val code = varchar("code", 255).nullable()
    val diagnosisList = varchar("diagnosis_list", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица lpu - лечебно-профилактические учреждения
object Lpu : Table("lpu") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255)
    val rayId = integer("ray_id")
    val region = varchar("region", 255).nullable()
    val columnFData = varchar("column_f_data", 255).nullable()
    val columnGData = varchar("column_g_data", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица raion - районы
object Raion : Table("raion") {
    val id = integer("id").autoIncrement()
    val nameRaion = varchar("name_raion", 255).nullable()
    val type = varchar("type", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица service - услуги
object Service : Table("service") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255).nullable()
    val code = varchar("code", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица service_types - типы услуг
object ServiceTypes : Table("service_types") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица study_character - характеристики исследования
object StudyCharacter : Table("study_character") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица comments - комментарии
object Comments : Table("comments") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255)

    override val primaryKey = PrimaryKey(id)
}

// Таблица docnaprav - врачи-направители
object Docnaprav : Table("docnaprav") {
    val id = integer("id").autoIncrement()
    val doctorNapravitel = varchar("doctor_napravitel", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица gistolog - гистология
object Gistolog : Table("gistolog") {
    val id = integer("id").autoIncrement()
    val gistName = varchar("gist_name", 255).nullable()
    val gisologCommentText = varchar("gisolog_comment_text", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица loc - локализация
object Loc : Table("loc") {
    val id = integer("id").autoIncrement()
    val location = text("location")

    override val primaryKey = PrimaryKey(id)
}

// Таблица organ - органы
object Organ : Table("organ") {
    val id = varchar("id", 255)
    val nameOrgan = text("name_organ").nullable()
    val nameShort = text("name_short").nullable()
    val medicalSubjectName = text("medical_subject_name").nullable()
    val regionId = varchar("region_id", 255).nullable()
    val regionName = text("region_name").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица profosmotr - профосмотры
object Profosmotr : Table("profosmotr") {
    val id = integer("id").autoIncrement()
    val fullName = varchar("full_name", 255).nullable()
    val birthdate = date("birthdate").nullable()
    val snils = varchar("snils", 14).nullable()
    val lpu = varchar("lpu", 255).nullable()
    val result = varchar("result", 255).nullable()
    val date = date("date").nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица ecp45mis - учетные данные для МИС
object Ecp45mis : Table("ecp45mis") {
    val id = integer("id").autoIncrement()
    val login = varchar("login", 255).nullable()
    val password = varchar("password", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}

// Таблица swrat - справочник (предположительно)
object Swrat : Table("swrat") {
    val id = integer("id").autoIncrement()
    val name = varchar("name", 255).nullable()

    override val primaryKey = PrimaryKey(id)
}
