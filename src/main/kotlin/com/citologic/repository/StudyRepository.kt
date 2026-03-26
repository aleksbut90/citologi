package com.citologic.repository

import com.citologic.model.*
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.SqlExpressionBuilder.eq
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.stereotype.Repository
import java.time.LocalDate

@Repository
class StudyRepository {

    fun findAll(): List<StudyDto> = transaction {
        Studies.selectAll()
            .map { row ->
                StudyDto(
                    id = row[Studies.id],
                    studyDate = row[Studies.studyDate],
                    doctorId = row[Studies.doctorId],
                    labTechnicianId = row[Studies.labTechnicianId],
                    isReviewed = row[Studies.isReviewed],
                    znoDno = row[Studies.znoDno],
                    serviceId = row[Studies.serviceId],
                    urgencyId = row[Studies.urgencyId],
                    studyTypeId = row[Studies.studyTypeId],
                    isFluid = row[Studies.isFluid],
                    slidesCount = row[Studies.slidesCount],
                    transferredToDoctor = row[Studies.transferredToDoctor],
                    bethesdaTermId = row[Studies.bethesdaTermId],
                    pathologiesCount = row[Studies.pathologiesCount],
                    comment = row[Studies.comment],
                    patientId = row[Studies.patientId],
                    barcode = row[Studies.barcode],
                    materialId = row[Studies.materialId],
                    conclusionText = row[Studies.conclusionText],
                    version = row[Studies.version],
                    lockedByUserId = row[Studies.lockedByUserId],
                    lockedAt = row[Studies.lockedAt]
                )
            }
    }

    fun findById(id: Int): StudyDto? = transaction {
        Studies.select { Studies.id eq id }
            .map { row ->
                StudyDto(
                    id = row[Studies.id],
                    studyDate = row[Studies.studyDate],
                    doctorId = row[Studies.doctorId],
                    labTechnicianId = row[Studies.labTechnicianId],
                    isReviewed = row[Studies.isReviewed],
                    znoDno = row[Studies.znoDno],
                    serviceId = row[Studies.serviceId],
                    urgencyId = row[Studies.urgencyId],
                    studyTypeId = row[Studies.studyTypeId],
                    isFluid = row[Studies.isFluid],
                    slidesCount = row[Studies.slidesCount],
                    transferredToDoctor = row[Studies.transferredToDoctor],
                    bethesdaTermId = row[Studies.bethesdaTermId],
                    pathologiesCount = row[Studies.pathologiesCount],
                    comment = row[Studies.comment],
                    patientId = row[Studies.patientId],
                    barcode = row[Studies.barcode],
                    materialId = row[Studies.materialId],
                    conclusionText = row[Studies.conclusionText],
                    version = row[Studies.version],
                    lockedByUserId = row[Studies.lockedByUserId],
                    lockedAt = row[Studies.lockedAt]
                )
            }
            .singleOrNull()
    }

    fun findByPatientId(patientId: Int): List<StudyDto> = transaction {
        Studies.select { Studies.patientId eq patientId }
            .map { row ->
                StudyDto(
                    id = row[Studies.id],
                    studyDate = row[Studies.studyDate],
                    doctorId = row[Studies.doctorId],
                    labTechnicianId = row[Studies.labTechnicianId],
                    isReviewed = row[Studies.isReviewed],
                    znoDno = row[Studies.znoDno],
                    serviceId = row[Studies.serviceId],
                    urgencyId = row[Studies.urgencyId],
                    studyTypeId = row[Studies.studyTypeId],
                    isFluid = row[Studies.isFluid],
                    slidesCount = row[Studies.slidesCount],
                    transferredToDoctor = row[Studies.transferredToDoctor],
                    bethesdaTermId = row[Studies.bethesdaTermId],
                    pathologiesCount = row[Studies.pathologiesCount],
                    comment = row[Studies.comment],
                    patientId = row[Studies.patientId],
                    barcode = row[Studies.barcode],
                    materialId = row[Studies.materialId],
                    conclusionText = row[Studies.conclusionText],
                    version = row[Studies.version],
                    lockedByUserId = row[Studies.lockedByUserId],
                    lockedAt = row[Studies.lockedAt]
                )
            }
    }

    fun save(
        caseNumber: String?,
        patientFio: String?,
        studyDate: LocalDate?,
        conclusion: String?
    ): StudyDto = transaction {
        // Сначала ищем или создаем пациента
        val patientId = if (!patientFio.isNullOrBlank()) {
            val existingPatient = Patients.select { Patients.fullName eq patientFio }.singleOrNull()
            existingPatient?.get(Patients.id) ?: Patients.insert {
                it[Patients.fullName] = patientFio
            } get Patients.id
        } else null

        val id = Studies.insert {
            caseNumber?.let { cn -> it[Studies.barcode] = cn }
            studyDate?.let { sd -> it[Studies.studyDate] = sd }
            patientId?.let { pid -> it[Studies.patientId] = pid }
            conclusion?.let { c -> it[Studies.conclusionText] = c }
        } get Studies.id

        StudyDto(
            id = id,
            studyDate = studyDate ?: LocalDate.now(),
            doctorId = null,
            labTechnicianId = null,
            isReviewed = false,
            znoDno = null,
            serviceId = null,
            urgencyId = null,
            studyTypeId = null,
            isFluid = false,
            slidesCount = null,
            transferredToDoctor = null,
            bethesdaTermId = null,
            pathologiesCount = null,
            comment = null,
            patientId = patientId,
            barcode = caseNumber,
            materialId = null,
            conclusionText = conclusion,
            version = 0,
            lockedByUserId = null,
            lockedAt = null
        )
    }

    fun create(
        studyDate: LocalDate,
        doctorId: String? = null,
        labTechnicianId: String? = null,
        isReviewed: Boolean? = null,
        znoDno: String? = null,
        serviceId: Int? = null,
        urgencyId: Int? = null,
        studyTypeId: Int? = null,
        isFluid: Boolean? = null,
        slidesCount: Int? = null,
        transferredToDoctor: Int? = null,
        bethesdaTermId: String? = null,
        pathologiesCount: Int? = null,
        comment: String? = null,
        patientId: Int? = null,
        barcode: String? = null,
        materialId: Int? = null,
        conclusionText: String? = null
    ): StudyDto = transaction {
        val id = Studies.insert {
            it[Studies.studyDate] = studyDate
            doctorId?.let { did -> it[Studies.doctorId] = did }
            labTechnicianId?.let { lid -> it[Studies.labTechnicianId] = lid }
            isReviewed?.let { ir -> it[Studies.isReviewed] = ir }
            znoDno?.let { zd -> it[Studies.znoDno] = zd }
            serviceId?.let { sid -> it[Studies.serviceId] = sid }
            urgencyId?.let { uid -> it[Studies.urgencyId] = uid }
            studyTypeId?.let { stid -> it[Studies.studyTypeId] = stid }
            isFluid?.let { ifl -> it[Studies.isFluid] = ifl }
            slidesCount?.let { sc -> it[Studies.slidesCount] = sc }
            transferredToDoctor?.let { ttd -> it[Studies.transferredToDoctor] = ttd }
            bethesdaTermId?.let { btid -> it[Studies.bethesdaTermId] = btid }
            pathologiesCount?.let { pc -> it[Studies.pathologiesCount] = pc }
            comment?.let { c -> it[Studies.comment] = c }
            patientId?.let { pid -> it[Studies.patientId] = pid }
            barcode?.let { bc -> it[Studies.barcode] = bc }
            materialId?.let { mid -> it[Studies.materialId] = mid }
            conclusionText?.let { ct -> it[Studies.conclusionText] = ct }
        } get Studies.id

        StudyDto(
            id = id,
            studyDate = studyDate,
            doctorId = doctorId,
            labTechnicianId = labTechnicianId,
            isReviewed = isReviewed,
            znoDno = znoDno,
            serviceId = serviceId,
            urgencyId = urgencyId,
            studyTypeId = studyTypeId,
            isFluid = isFluid,
            slidesCount = slidesCount,
            transferredToDoctor = transferredToDoctor,
            bethesdaTermId = bethesdaTermId,
            pathologiesCount = pathologiesCount,
            comment = comment,
            patientId = patientId,
            barcode = barcode,
            materialId = materialId,
            conclusionText = conclusionText,
            version = 0,
            lockedByUserId = null,
            lockedAt = null
        )
    }

    fun update(
        id: Int,
        studyDate: LocalDate? = null,
        doctorId: String? = null,
        labTechnicianId: String? = null,
        isReviewed: Boolean? = null,
        znoDno: String? = null,
        serviceId: Int? = null,
        urgencyId: Int? = null,
        studyTypeId: Int? = null,
        isFluid: Boolean? = null,
        slidesCount: Int? = null,
        transferredToDoctor: Int? = null,
        bethesdaTermId: String? = null,
        pathologiesCount: Int? = null,
        comment: String? = null,
        patientId: Int? = null,
        barcode: String? = null,
        materialId: Int? = null,
        conclusionText: String? = null
    ): Boolean = transaction {
        Studies.update({ Studies.id eq id }) { studyUpdate ->
            studyDate?.let { studyUpdate[Studies.studyDate] = studyDate }
            doctorId?.let { studyUpdate[Studies.doctorId] = doctorId }
            labTechnicianId?.let { studyUpdate[Studies.labTechnicianId] = labTechnicianId }
            isReviewed?.let { studyUpdate[Studies.isReviewed] = isReviewed }
            znoDno?.let { studyUpdate[Studies.znoDno] = znoDno }
            serviceId?.let { studyUpdate[Studies.serviceId] = serviceId }
            urgencyId?.let { studyUpdate[Studies.urgencyId] = urgencyId }
            studyTypeId?.let { studyUpdate[Studies.studyTypeId] = studyTypeId }
            isFluid?.let { studyUpdate[Studies.isFluid] = isFluid }
            slidesCount?.let { studyUpdate[Studies.slidesCount] = slidesCount }
            transferredToDoctor?.let { studyUpdate[Studies.transferredToDoctor] = transferredToDoctor }
            bethesdaTermId?.let { studyUpdate[Studies.bethesdaTermId] = bethesdaTermId }
            pathologiesCount?.let { studyUpdate[Studies.pathologiesCount] = pathologiesCount }
            comment?.let { studyUpdate[Studies.comment] = comment }
            patientId?.let { studyUpdate[Studies.patientId] = patientId }
            barcode?.let { studyUpdate[Studies.barcode] = barcode }
            materialId?.let { studyUpdate[Studies.materialId] = materialId }
            conclusionText?.let { studyUpdate[Studies.conclusionText] = conclusionText }
        } > 0
    }

    fun deleteById(id: Int): Boolean = transaction {
        Studies.deleteWhere { Studies.id eq id } > 0
    }
    
    // Методы для загрузки справочников
    fun findAllServices(): List<Pair<Int, String>> = try { transaction {
        Services.selectAll().map { row ->
            Pair(row[Services.id], row[Services.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllResearchTypes(): List<Pair<Int, String>> = try { transaction {
        ResearchTypes.selectAll().map { row ->
            Pair(row[ResearchTypes.id], row[ResearchTypes.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllMaterialTypes(): List<Pair<Int, String>> = try { transaction {
        MaterialTypes.selectAll().map { row ->
            Pair(row[MaterialTypes.id], row[MaterialTypes.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllGistologConclusions(): List<Pair<Int, String>> = try { transaction {
        Gistolog.selectAll().map { row ->
            Pair(row[Gistolog.id], row[Gistolog.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllStudyTypes(): List<Pair<Int, String>> = try { transaction {
        StudyTypes.selectAll().map { row ->
            Pair(row[StudyTypes.id], row[StudyTypes.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllBethesdaTerms(): List<Pair<Int, String>> = try { transaction {
        BethesdaTerms.selectAll().map { row ->
            Pair(row[BethesdaTerms.id], row[BethesdaTerms.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllZnoDno(): List<Pair<Int, String>> = try { transaction {
        ZnoDno.selectAll().map { row ->
            Pair(row[ZnoDno.id], row[ZnoDno.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllUrgencies(): List<Pair<Int, String>> = try { transaction {
        Urgencies.selectAll().map { row ->
            Pair(row[Urgencies.id], row[Urgencies.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllComments(): List<Pair<Int, String>> = try { transaction {
        Comments.selectAll().map { row ->
            Pair(row[Comments.id], row[Comments.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllLocalizations(): List<Pair<Int, String>> = try { transaction {
        Localizations.selectAll().map { row ->
            Pair(row[Localizations.id], row[Localizations.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
    
    fun findAllCiphers(): List<Pair<Int, String>> = try { transaction {
        CodeCytology.selectAll().map { row ->
            Pair(row[CodeCytology.id], row[CodeCytology.name])
        }.distinctBy { it.first }
    }} catch (e: Exception) { emptyList() }
}

data class StudyDto(
    val id: Int,
    val studyDate: LocalDate,
    val doctorId: String?,
    val labTechnicianId: String?,
    val isReviewed: Boolean?,
    val znoDno: String?,
    val serviceId: Int?,
    val urgencyId: Int?,
    val studyTypeId: Int?,
    val isFluid: Boolean?,
    val slidesCount: Int?,
    val transferredToDoctor: Int?,
    val bethesdaTermId: String?,
    val pathologiesCount: Int?,
    val comment: String?,
    val patientId: Int?,
    val barcode: String?,
    val materialId: Int?,
    val conclusionText: String?,
    val version: Int,
    val lockedByUserId: String?,
    val lockedAt: java.time.Instant?
) {
    val labTechnician: String? get() = labTechnicianId // Для совместимости с HomeView
    
    companion object {
        fun fromRow(row: ResultRow): StudyDto {
            return StudyDto(
                id = row[Studies.id],
                studyDate = row[Studies.studyDate],
                doctorId = row[Studies.doctorId],
                labTechnicianId = row[Studies.labTechnicianId],
                isReviewed = row[Studies.isReviewed],
                znoDno = row[Studies.znoDno],
                serviceId = row[Studies.serviceId],
                urgencyId = row[Studies.urgencyId],
                studyTypeId = row[Studies.studyTypeId],
                isFluid = row[Studies.isFluid],
                slidesCount = row[Studies.slidesCount],
                transferredToDoctor = row[Studies.transferredToDoctor],
                bethesdaTermId = row[Studies.bethesdaTermId],
                pathologiesCount = row[Studies.pathologiesCount],
                comment = row[Studies.comment],
                patientId = row[Studies.patientId],
                barcode = row[Studies.barcode],
                materialId = row[Studies.materialId],
                conclusionText = row[Studies.conclusionText],
                version = row[Studies.version],
                lockedByUserId = row[Studies.lockedByUserId],
                lockedAt = row[Studies.lockedAt]
            )
        }
    }
}
