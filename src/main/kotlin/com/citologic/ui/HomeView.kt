package com.citologic.ui

import com.citologic.model.*
import com.citologic.repository.UserRepository
import com.vaadin.flow.component.*
import com.vaadin.flow.component.button.Button
import com.vaadin.flow.component.button.ButtonVariant
import com.vaadin.flow.component.checkbox.Checkbox
import com.vaadin.flow.component.combobox.ComboBox
import com.vaadin.flow.component.datepicker.DatePicker
import com.vaadin.flow.component.dialog.Dialog
import com.vaadin.flow.component.formlayout.FormLayout
import com.vaadin.flow.component.grid.Grid
import com.vaadin.flow.component.html.*
import com.vaadin.flow.component.icon.VaadinIcon
import com.vaadin.flow.component.notification.Notification
import com.vaadin.flow.component.orderedlayout.*
import com.vaadin.flow.component.textfield.IntegerField
import com.vaadin.flow.component.textfield.TextArea
import com.vaadin.flow.component.textfield.TextField
import com.vaadin.flow.data.binder.Binder
import com.vaadin.flow.router.BeforeEnterEvent
import com.vaadin.flow.router.BeforeEnterObserver
import com.vaadin.flow.router.Route
import com.vaadin.flow.server.VaadinSession
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.transactions.transaction
import org.springframework.beans.factory.annotation.Autowired
import java.time.LocalDate
import java.time.format.DateTimeFormatter

@Route("")
class HomeView : VerticalLayout(), BeforeEnterObserver {

    @Autowired
    private lateinit var userRepository: UserRepository

    // Общие сведения
    private val caseNumberField = TextField("Номер стекла")
    private val ambulatorySearchField = TextField("Амбулаторная карта")
    private val directionField = TextField("Номер направления")
    private val peresmotrCheckbox = Checkbox("Пересмотр")

    // Пациент
    private val patientLastNameField = TextField("Фамилия")
    private val patientFirstNameField = TextField("Имя")
    private val patientMiddleNameField = TextField("Отчество")
    private val birthDateField = DatePicker("Дата рождения")
    private val ageField = TextField("Возраст") { isEnabled = false }
    private val genderComboBox = ComboBox<String>("Пол").apply {
        items = listOf("Женский", "Мужской")
        value = "Женский"
    }
    private val snilsField = TextField("СНИЛС")
    private val raionComboBox = ComboBox<String>("Район")
    private val addressField = TextField("Адрес проживания")
    private val insuranceField = TextField("Полис")
    private val isDismissedField = DatePicker("Снят с учета")
    private val ambulatoryCardNumberField = TextField("Номер амбулаторной карты")
    private val isEmployedCheckbox = Checkbox("Трудоустроен")

    // Поступление материала
    private val directionNumberField = TextField("Номер направления")
    private val medicalOrganizationComboBox = ComboBox<String>("Медицинская организация")
    private val receiptDateField = DatePicker("Дата поступления")
    private val slidesCountField = IntegerField("Количество стеклопрепаратов")
    private val departmentComboBox = ComboBox<String>("Отделение")
    private val referringDoctorComboBox = ComboBox<String>("Врач-направитель")
    private val researchTypeComboBox = ComboBox<String>("Характер исследования")
    private val clinicalDiagnosisComboBox = ComboBox<String>("Клинический диагноз (МКБ-10)")
    private val localizationComboBox = ComboBox<String>("Локализация")
    private val ciphersComboBox = ComboBox<String>("Шифр локализаций")
    private val materialTypeComboBox = ComboBox<String>("Характер материала")
    private val gistMatikComboBox = ComboBox<String>("Заключение гистолога")
    private val histologicallyConfirmedCheckbox = Checkbox("Подтвержден гистологически")
    private val conclusionMatchedCheckbox = Checkbox("Заключение совпало")

    // Результаты исследования
    private val studyDateField = DatePicker("Дата исследования")
    private val doctorComboBox = ComboBox<String>("Врач")
    private val labTechnicianComboBox = ComboBox<String>("Лаборант")
    private val znoDnoComboBox = ComboBox<String>("Просмотр ЗНО/ДНО")
    private val serviceComboBox = ComboBox<String>("Услуга")
    private val conclusionTextArea = TextArea("Текст заключения")
    private val commentComboBox = ComboBox<String>("Комментарий")

    // Кнопки
    private val createNewStudyButton = Button("Создать новое исследование")
    private val printReferralButton = Button("Печатать направление")
    private val overviewButton = Button("Общие данные")
    private val profilaktikaButton = Button("Профосмотр")
    private val reportButton = Button("Страница отчетов")
    private val logoutButton = Button("Выход")
    private val findPatientButton = Button("Найти пациента")
    private val saveButton = Button("Сохранить")
    private val createCopyButton = Button("Создать копию") { isVisible = false }

    // Модальные окна
    private val studiesOverviewDialog = Dialog()
    private val studyDetailsDialog = Dialog()
    private val patientSearchDialog = Dialog()

    // Таблица исследований
    private val studiesGrid = Grid<StudyRow>()

    data class StudyRow(
        val id: Int,
        val studyDate: String,
        val labTechnician: String,
        val isFluid: Boolean,
        val barcode: String?
    )

    init {
        setSizeFull()
        addClassName("home-view")
        
        setupHeader()
        setupControls()
        setupGeneralInfoSection()
        setupPatientSection()
        setupMaterialSection()
        setupResultsSection()
        setupStudiesTable()
        setupModals()
        loadData()
    }

    private fun setupHeader() {
        val header = HorizontalLayout().apply {
            setWidthFull()
            justifyContentMode = JustifyContentMode.BETWEEN
            alignItems = Alignment.CENTER
            addClassName("header")
            
            val title = H1("Цитологическая служба")
            
            val userInfo = HorizontalLayout().apply {
                val session = VaadinSession.getCurrent()
                val userFIO = session.getAttribute("userFIO") as? String ?: "Сотрудник"
                val userStatus = session.getAttribute("userStatus") as? String ?: "USER"
                
                add(Span("Сотрудник: $userFIO"))
                addClassName("user-info")
            }
            
            add(title, userInfo)
        }
        
        add(header)
    }

    private fun setupControls() {
        val controlsLayout = HorizontalLayout().apply {
            setWidthFull()
            justifyContentMode = JustifyContentMode.START
            spacing = true
            addClassName("controls")
            
            createNewStudyButton.addClickListener { createNewStudy() }
            printReferralButton.addClickListener { printReferral() }
            overviewButton.addClickListener { showStudiesOverview() }
            profilaktikaButton.addClickListener { showProfilaktika() }
            reportButton.addClickListener { showReports() }
            logoutButton.addClickListener { logout() }
            
            add(createNewStudyButton, printReferralButton, overviewButton, 
                profilaktikaButton, reportButton, logoutButton)
        }
        
        add(controlsLayout)
    }

    private fun setupGeneralInfoSection() {
        val section = Card().apply {
            addClassName("general-info-section")
            
            val title = H4("Общие сведения")
            
            val formLayout = FormLayout().apply {
                setWidthFull()
                
                addFormItem(caseNumberField, "Номер стекла")
                addFormItem(ambulatorySearchField, "Амбулаторная карта")
                addFormItem(directionField, "Номер направления")
                
                val peresmotrLayout = HorizontalLayout(peresmotrCheckbox).apply {
                    setPadding(false)
                }
                addFormItem(peresmotrLayout, "")
            }
            
            add(title, formLayout)
        }
        
        add(section)
    }

    private fun setupPatientSection() {
        val section = Card().apply {
            addClassName("patient-section")
            
            val title = H4("Пациент")
            
            val findPatientBtn = Button("Найти пациента") { showPatientSearch() }
            
            val formLayout = FormLayout().apply {
                setWidthFull()
                responsiveSteps = FormLayout.ResponsiveStep("0", 2)
                
                add(findPatientBtn)
                addFormItem(patientLastNameField, "Фамилия")
                addFormItem(patientFirstNameField, "Имя")
                addFormItem(patientMiddleNameField, "Отчество")
                addFormItem(birthDateField, "Дата рождения")
                addFormItem(ageField, "Возраст")
                addFormItem(genderComboBox, "Пол")
                addFormItem(snilsField, "СНИЛС")
                addFormItem(raionComboBox, "Район")
                addFormItem(addressField, "Адрес проживания")
                addFormItem(insuranceField, "Полис")
                addFormItem(isDismissedField, "Снят с учета")
                addFormItem(ambulatoryCardNumberField, "Номер амбулаторной карты")
                
                val employedLayout = HorizontalLayout(isEmployedCheckbox).apply {
                    setPadding(false)
                }
                addFormItem(employedLayout, "Трудоустроен")
            }
            
            // Добавляем listener для расчета возраста
            birthDateField.addValueChangeListener { calculateAge() }
            
            add(title, formLayout)
        }
        
        add(section)
    }

    private fun setupMaterialSection() {
        val section = Card().apply {
            addClassName("material-section")
            
            val title = H4("Поступление материала")
            
            val formLayout = FormLayout().apply {
                setWidthFull()
                responsiveSteps = FormLayout.ResponsiveStep("0", 2)
                
                addFormItem(directionNumberField, "Номер направления")
                addFormItem(medicalOrganizationComboBox, "Медицинская организация")
                addFormItem(receiptDateField, "Дата поступления")
                addFormItem(slidesCountField, "Количество стеклопрепаратов")
                addFormItem(departmentComboBox, "Отделение")
                addFormItem(referringDoctorComboBox, "Врач-направитель")
                addFormItem(researchTypeComboBox, "Характер исследования")
                addFormItem(clinicalDiagnosisComboBox, "Клинический диагноз (МКБ-10)")
                addFormItem(localizationComboBox, "Локализация")
                addFormItem(ciphersComboBox, "Шифр локализаций")
                addFormItem(materialTypeComboBox, "Характер материала")
                addFormItem(gistMatikComboBox, "Заключение гистолога")
                
                val histologyLayout = HorizontalLayout(histologicallyConfirmedCheckbox).apply {
                    setPadding(false)
                }
                addFormItem(histologyLayout, "Подтвержден гистологически")
                
                val conclusionLayout = HorizontalLayout(conclusionMatchedCheckbox).apply {
                    setPadding(false)
                }
                addFormItem(conclusionLayout, "Заключение совпало")
            }
            
            add(title, formLayout)
        }
        
        add(section)
    }

    private fun setupResultsSection() {
        val section = Card().apply {
            addClassName("results-section")
            
            val title = H4("Результаты исследования")
            
            val formLayout = FormLayout().apply {
                setWidthFull()
                responsiveSteps = FormLayout.ResponsiveStep("0", 2)
                
                addFormItem(studyDateField, "Дата исследования")
                addFormItem(doctorComboBox, "Врач")
                addFormItem(labTechnicianComboBox, "Лаборант")
                addFormItem(znoDnoComboBox, "Просмотр ЗНО/ДНО")
                addFormItem(serviceComboBox, "Услуга")
                addFormItem(conclusionTextArea, "Текст заключения")
                addFormItem(commentComboBox, "Комментарий")
                
                val buttonsLayout = HorizontalLayout(saveButton, createCopyButton).apply {
                    spacing = true
                    setPadding(false)
                }
                add(buttonsLayout)
            }
            
            saveButton.addClickListener { saveStudy() }
            
            // Показываем кнопку создания копии только если выбран пересмотр
            peresmotrCheckbox.addValueChangeListener { event ->
                createCopyButton.isVisible = event.value
            }
            
            add(title, formLayout)
        }
        
        add(section)
    }

    private fun setupStudiesTable() {
        val section = Card().apply {
            addClassName("studies-table-section")
            
            val title = H4("Исследования")
            
            studiesGrid.apply {
                setSizeFull()
                addColumn(StudyRow::id).setHeader("ID исследования").setKey("id")
                addColumn(StudyRow::studyDate).setHeader("Дата исследования").setKey("studyDate")
                addColumn(StudyRow::labTechnician).setHeader("Лаборант").setKey("labTechnician")
                addColumn(StudyRow::isFluid).setHeader("Жидкостная").setKey("isFluid")
                    .setRenderer(ComponentRenderer { isFluid ->
                        if (isFluid) Text("Да") else Text("Нет")
                    })
                addColumn(StudyRow::barcode).setHeader("Штрихкод").setKey("barcode")
                
                // Колонка действий
                addColumn(ComponentRenderer { row ->
                    HorizontalLayout(
                        Button("Просмотр", { viewStudyDetails(row) }).apply {
                            themeNames = listOf(ButtonVariant.LUMO_TERTIARY.small)
                        },
                        Button("Редактировать", { editStudy(row) }).apply {
                            themeNames = listOf(ButtonVariant.LUMO_TERTIARY.small)
                        },
                        Button("Удалить", { deleteStudy(row) }).apply {
                            themeNames = listOf(ButtonVariant.LUMO_ERROR.small)
                        }
                    ).apply { spacing = true }
                }).setHeader("Действия")
            }
            
            add(title, studiesGrid)
        }
        
        add(section)
    }

    private fun setupModals() {
        // Модальное окно общих данных исследований
        studiesOverviewDialog.apply {
            width = "90%"
            maxWidth = "1200px"
            
            val content = VerticalLayout().apply {
                setPadding(true)
                setSpacing(true)
                
                add(H2("Общие данные исследований"))
                
                // Фильтры
                val filtersLayout = setupOverviewFilters()
                add(filtersLayout)
                
                // Таблица
                val overviewGrid = Grid<StudyRow>().apply {
                    setSizeFull()
                    addColumn(StudyRow::id).setHeader("ID исследования")
                    addColumn(StudyRow::studyDate).setHeader("Дата исследования")
                    addColumn(StudyRow::labTechnician).setHeader("Лаборант")
                    addColumn(StudyRow::isFluid).setHeader("Жидкостная")
                        .setRenderer(ComponentRenderer { isFluid ->
                            if (isFluid) Text("Да") else Text("Нет")
                        })
                    addColumn(StudyRow::barcode).setHeader("Штрихкод")
                    
                    addColumn(ComponentRenderer { row ->
                        HorizontalLayout(
                            Button("Просмотр", { viewStudyDetails(row) }),
                            Button("Редактировать", { editStudy(row) }),
                            Button("Удалить", { deleteStudy(row) }).apply {
                                themeNames = listOf("error")
                            }
                        ).apply { spacing = true }
                    }).setHeader("Действия")
                }
                
                val countLabel = Span("Количество исследований: 0")
                countLabel.setId("studiesCountValue")
                
                add(countLabel, overviewGrid)
            }
            
            add(content)
            
            val closeButton = Button("×") { close() }
            closeButton.addClassName("close-button")
            header?.add(closeButton)
        }

        // Модальное окно деталей исследования
        studyDetailsDialog.apply {
            width = "90%"
            maxWidth = "1000px"
            
            val content = VerticalLayout().apply {
                setPadding(true)
                add(H2("Детали исследования"))
                add(Div().apply { 
                    text = "Здесь будут отображены детали исследования"
                    setPadding(true)
                })
            }
            
            add(content)
            
            val closeButton = Button("×") { close() }
            closeButton.addClassName("close-button")
            header?.add(closeButton)
        }

        // Модальное окно поиска пациента
        patientSearchDialog.apply {
            width = "500px"
            
            val content = VerticalLayout().apply {
                setPadding(true)
                setSpacing(true)
                
                add(H3("Поиск пациента"))
                
                val searchField = TextField("ФИО или СНИЛС")
                val searchButton = Button("Найти") {
                    // Логика поиска пациента
                    Notification.show("Поиск пациента...", 3000, Notification.Position.BOTTOM_CENTER)
                }
                
                val resultsGrid = Grid<PatientRow>().apply {
                    setSizeFull()
                    addColumn(PatientRow::fio).setHeader("ФИО")
                    addColumn(PatientRow::birthDate).setHeader("Дата рождения")
                    addColumn(PatientRow::snils).setHeader("СНИЛС")
                    
                    addColumn(ComponentRenderer { row ->
                        Button("Выбрать") {
                            selectPatient(row)
                            patientSearchDialog.close()
                        }
                    }).setHeader("Действие")
                }
                
                add(searchField, searchButton, resultsGrid)
            }
            
            add(content)
            
            val closeButton = Button("×") { close() }
            closeButton.addClassName("close-button")
            header?.add(closeButton)
        }
    }

    data class PatientRow(
        val id: Int,
        val fio: String,
        val birthDate: String,
        val snils: String?
    )

    private fun setupOverviewFilters(): Component {
        return VerticalLayout().apply {
            setWidthFull()
            
            val dateFilterComboBox = ComboBox<String>("Фильтр по дате").apply {
                items = listOf("Все", "Сегодня", "Этот месяц", "Произвольный диапазон")
                value = "Все"
            }
            
            val customDateRange = HorizontalLayout().apply {
                isVisible = false
                add(DatePicker("От"), DatePicker("До"))
            }
            
            dateFilterComboBox.addValueChangeListener { event ->
                customDateRange.isVisible = event.value == "Произвольный диапазон"
            }
            
            val serviceFilter = ComboBox<String>("Услуга").apply {
                items = listOf("", "Все услуги")
                value = ""
            }
            
            val applyButton = Button("Применить")
            val resetButton = Button("Сбросить")
            
            val searchLayout = HorizontalLayout(
                TextField("Поиск стекла").apply { placeholder = "ID исследования" },
                Button("Найти")
            )
            
            add(
                HorizontalLayout(dateFilterComboBox, serviceFilter, applyButton, resetButton).apply {
                    setWidthFull()
                    flexWrap = FlexWrap.WRAP
                },
                customDateRange,
                searchLayout
            )
        }
    }

    private fun loadData() {
        transaction {
            // Загрузка районов
            try {
                val raions = Raion.all().map { it.nameRaion ?: "" }.filter { it.isNotEmpty() }
                raionComboBox.items = raions
            } catch (e: Exception) {
                // Игнорируем ошибки загрузки
            }
            
            // Загрузка врачей
            try {
                val doctors = Physicians.all().filter { it.role == "doctor" }.map { it.fullName }
                doctorComboBox.items = doctors
            } catch (e: Exception) {
                doctorComboBox.items = emptyList()
            }
            
            // Загрузка лаборантов
            try {
                val labTechnicians = Physicians.all().filter { it.role == "lab_technician" }.map { it.fullName }
                labTechnicianComboBox.items = labTechnicians
            } catch (e: Exception) {
                labTechnicianComboBox.items = emptyList()
            }
            
            // Загрузка медицинских организаций
            try {
                val organizations = Organ.all().map { it.nameOrgan ?: "" }.filter { it.isNotEmpty() }
                medicalOrganizationComboBox.items = organizations
            } catch (e: Exception) {
                medicalOrganizationComboBox.items = emptyList()
            }
            
            // Загрузка отделений
            try {
                val departments = Otdel.all().map { it.department ?: "" }.filter { it.isNotEmpty() }
                departmentComboBox.items = departments
            } catch (e: Exception) {
                departmentComboBox.items = emptyList()
            }
            
            // Загрузка услуг
            try {
                val services = Service.all().map { it.name ?: "" }.filter { it.isNotEmpty() }
                serviceComboBox.items = services
            } catch (e: Exception) {
                serviceComboBox.items = emptyList()
            }
            
            // Загрузка комментариев
            try {
                val comments = Comments.all().map { it.name }
                commentComboBox.items = comments
            } catch (e: Exception) {
                commentComboBox.items = emptyList()
            }
            
            // Загрузка локализаций
            try {
                val localizations = Loc.all().map { it.location }
                localizationComboBox.items = localizations
            } catch (e: Exception) {
                localizationComboBox.items = emptyList()
            }
            
            // Загрузка Bethesda терминов
            try {
                val bethesdaTerms = Bethesda.all().map { it.fullName }
                gistMatikComboBox.items = bethesdaTerms
                znoDnoComboBox.items = bethesdaTerms
            } catch (e: Exception) {
                gistMatikComboBox.items = emptyList()
                znoDnoComboBox.items = emptyList()
            }
            
            // Загрузка МКБ
            try {
                val mkbCodes = Mkb.all().map { "${it.code} - ${it.diagnosisList}" }.filter { it.isNotBlank() }
                clinicalDiagnosisComboBox.items = mkbCodes
            } catch (e: Exception) {
                clinicalDiagnosisComboBox.items = emptyList()
            }
            
            // Загрузка врачей-направителей
            try {
                val referringDoctors = Docnaprav.all().map { it.doctorNapravitel ?: "" }.filter { it.isNotEmpty() }
                referringDoctorComboBox.items = referringDoctors
            } catch (e: Exception) {
                referringDoctorComboBox.items = emptyList()
            }
            
            // Загрузка характера исследования
            try {
                val researchTypes = StudyCharacter.all().map { it.name ?: "" }.filter { it.isNotEmpty() }
                researchTypeComboBox.items = researchTypes
            } catch (e: Exception) {
                researchTypeComboBox.items = emptyList()
            }
            
            // Загрузка типов материалов
            try {
                val materialTypes = SampleTypes.all().map { it.name }.distinct()
                materialTypeComboBox.items = materialTypes
            } catch (e: Exception) {
                materialTypeComboBox.items = emptyList()
            }
            
            // Загрузка шифров
            try {
                val ciphers = CodeCytology.all().map { "${it.codeSi} - ${it.nameCodeSi}" }.filter { it.isNotBlank() }
                ciphersComboBox.items = ciphers
            } catch (e: Exception) {
                ciphersComboBox.items = emptyList()
            }
        }
        
        loadStudiesGrid()
    }

    private fun loadStudiesGrid() {
        transaction {
            try {
                val studies = Studies.all().orderBy(Studies.id.desc()).limit(100).map { study ->
                    StudyRow(
                        id = study.id.value,
                        studyDate = study.studyDate.toString(),
                        labTechnician = study.labTechnicianId ?: "",
                        isFluid = study.isFluid ?: false,
                        barcode = study.barcode
                    )
                }
                studiesGrid.items = studies
            } catch (e: Exception) {
                studiesGrid.items = emptyList()
            }
        }
    }

    private fun calculateAge() {
        val birthDate = birthDateField.value
        if (birthDate != null) {
            val period = java.time.Period.between(birthDate, LocalDate.now())
            ageField.value = "${period.years} лет"
        } else {
            ageField.value = ""
        }
    }

    // Обработчики событий
    private fun createNewStudy() {
        clearForm()
        Notification.show("Создание нового исследования", 3000, Notification.Position.BOTTOM_CENTER)
    }

    private fun printReferral() {
        Notification.show("Печать направления...", 3000, Notification.Position.BOTTOM_CENTER)
    }

    private fun showStudiesOverview() {
        studiesOverviewDialog.open()
        loadStudiesGrid()
    }

    private fun showProfilaktika() {
        // Переход на страницу профосмотра
        UI.getCurrent().page.setLocation("profilaktika")
    }

    private fun showReports() {
        // Переход на страницу отчетов
        UI.getCurrent().page.setLocation("reports")
    }

    private fun logout() {
        VaadinSession.getCurrent().session.invalidate()
        UI.getCurrent().page.setLocation("login")
    }

    private fun showPatientSearch() {
        patientSearchDialog.open()
    }

    private fun selectPatient(patient: PatientRow) {
        // Заполнение полей данными пациента
        val fioParts = patient.fio.split(" ")
        patientLastNameField.value = fioParts.getOrElse(0) { "" }
        patientFirstNameField.value = fioParts.getOrElse(1) { "" }
        patientMiddleNameField.value = fioParts.getOrElse(2) { "" }
        snilsField.value = patient.snils ?: ""
        
        Notification.show("Пациент выбран: ${patient.fio}", 3000, Notification.Position.BOTTOM_CENTER)
    }

    private fun viewStudyDetails(row: StudyRow) {
        studyDetailsDialog.open()
    }

    private fun editStudy(row: StudyRow) {
        Notification.show("Редактирование исследования #${row.id}", 3000, Notification.Position.BOTTOM_CENTER)
    }

    private fun deleteStudy(row: StudyRow) {
        val confirmDialog = Dialog()
        confirmDialog.width = "400px"
        
        val content = VerticalLayout().apply {
            setPadding(true)
            setSpacing(true)
            
            add(H3("Подтверждение удаления"))
            add(Text("Вы уверены, что хотите удалить исследование #${row.id}?"))
            
            val buttons = HorizontalLayout(
                Button("Удалить", {
                    // Логика удаления
                    transaction {
                        try {
                            Studies.deleteWhere { Studies.id eq row.id }
                            Notification.show("Исследование удалено", 3000, Notification.Position.BOTTOM_CENTER)
                            loadStudiesGrid()
                        } catch (e: Exception) {
                            Notification.show("Ошибка при удалении: ${e.message}", 5000, Notification.Position.BOTTOM_CENTER)
                        }
                    }
                    confirmDialog.close()
                    studiesOverviewDialog.close()
                }).apply { themeNames = listOf("error", "primary") },
                Button("Отмена", { confirmDialog.close() }).apply { themeNames = listOf("tertiary") }
            ).apply { spacing = true }
            
            add(buttons)
        }
        
        confirmDialog.add(content)
        confirmDialog.open()
    }

    private fun saveStudy() {
        transaction {
            try {
                // Сохранение данных исследования
                Notification.show("Исследование сохранено", 3000, Notification.Position.BOTTOM_CENTER)
                loadStudiesGrid()
            } catch (e: Exception) {
                Notification.show("Ошибка при сохранении: ${e.message}", 5000, Notification.Position.BOTTOM_CENTER)
            }
        }
    }

    private fun clearForm() {
        // Очистка всех полей формы
        caseNumberField.clear()
        ambulatorySearchField.clear()
        directionField.clear()
        peresmotrCheckbox.value = false
        
        patientLastNameField.clear()
        patientFirstNameField.clear()
        patientMiddleNameField.clear()
        birthDateField.clear()
        ageField.clear()
        genderComboBox.value = "Женский"
        snilsField.clear()
        raionComboBox.clear()
        addressField.clear()
        insuranceField.clear()
        isDismissedField.clear()
        ambulatoryCardNumberField.clear()
        isEmployedCheckbox.value = false
        
        directionNumberField.clear()
        medicalOrganizationComboBox.clear()
        receiptDateField.clear()
        slidesCountField.clear()
        departmentComboBox.clear()
        referringDoctorComboBox.clear()
        researchTypeComboBox.clear()
        clinicalDiagnosisComboBox.clear()
        localizationComboBox.clear()
        ciphersComboBox.clear()
        materialTypeComboBox.clear()
        gistMatikComboBox.clear()
        histologicallyConfirmedCheckbox.value = false
        conclusionMatchedCheckbox.value = false
        
        studyDateField.value = LocalDate.now()
        doctorComboBox.clear()
        labTechnicianComboBox.clear()
        znoDnoComboBox.clear()
        serviceComboBox.clear()
        conclusionTextArea.clear()
        commentComboBox.clear()
    }

    override fun beforeEnter(event: BeforeEnterEvent) {
        val auth = org.springframework.security.core.context.SecurityContextHolder.getContext().authentication
        
        if (auth == null || !auth.isAuthenticated || 
            auth is org.springframework.security.authentication.AnonymousAuthenticationToken) {
            event.rerouteTo("login")
        }
    }
}
