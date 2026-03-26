package com.citologic.ui

import com.citologic.model.*
import com.citologic.repository.PatientRepository
import com.citologic.repository.StudyRepository
import com.citologic.repository.UserRepository
import com.citologic.ui.components.Card
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
import com.vaadin.flow.component.notification.Notification
import com.vaadin.flow.component.orderedlayout.FlexComponent
import com.vaadin.flow.component.orderedlayout.FlexLayout
import com.vaadin.flow.component.orderedlayout.HorizontalLayout
import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.component.progressbar.ProgressBar
import com.vaadin.flow.component.textfield.IntegerField
import com.vaadin.flow.component.textfield.TextArea
import com.vaadin.flow.component.textfield.TextField
import com.vaadin.flow.data.renderer.ComponentRenderer
import com.vaadin.flow.router.BeforeEnterEvent
import com.vaadin.flow.router.BeforeEnterObserver
import com.vaadin.flow.router.Route
import com.vaadin.flow.server.VaadinSession
import kotlinx.coroutines.*
import org.springframework.beans.factory.annotation.Autowired
import java.time.LocalDate
import java.time.Period

@Route("")
class HomeView : VerticalLayout(), BeforeEnterObserver {

    @Autowired
    private lateinit var userRepository: UserRepository

    @Autowired
    private lateinit var patientRepository: PatientRepository

    @Autowired
    private lateinit var studyRepository: StudyRepository

    // Coroutine scopes
    private val uiScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val ioScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // Progress bar
    private val progressBar = ProgressBar().apply {
        isVisible = false
        isIndeterminate = true
    }

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
        setItems(listOf("Женский", "Мужской"))
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
        
        add(progressBar)
        
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
            justifyContentMode = FlexComponent.JustifyContentMode.BETWEEN
            alignItems = FlexComponent.Alignment.CENTER
            addClassName("header")
            
            val title = H1("Цитологическая служба")
            
            val userInfo = HorizontalLayout().apply {
                val session = VaadinSession.getCurrent()
                val userFIO = session.getAttribute("userFIO") as? String ?: "Сотрудник"
                
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
            justifyContentMode = FlexComponent.JustifyContentMode.START
            isSpacing = true
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
                responsiveSteps = listOf(FormLayout.ResponsiveStep("0", 2))
                
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
                responsiveSteps = listOf(FormLayout.ResponsiveStep("0", 2))
                
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
                responsiveSteps = listOf(FormLayout.ResponsiveStep("0", 2))
                
                addFormItem(studyDateField, "Дата исследования")
                addFormItem(doctorComboBox, "Врач")
                addFormItem(labTechnicianComboBox, "Лаборант")
                addFormItem(znoDnoComboBox, "Просмотр ЗНО/ДНО")
                addFormItem(serviceComboBox, "Услуга")
                addFormItem(conclusionTextArea, "Текст заключения")
                addFormItem(commentComboBox, "Комментарий")
                
                val buttonsLayout = HorizontalLayout(saveButton, createCopyButton).apply {
                    isSpacing = true
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
                addColumn { row -> row.id }.setHeader("ID исследования").setKey("id")
                addColumn { row -> row.studyDate }.setHeader("Дата исследования").setKey("studyDate")
                addColumn { row -> row.labTechnician }.setHeader("Лаборант").setKey("labTechnician")
                addColumn { row -> if (row.isFluid) "Да" else "Нет" }.setHeader("Жидкостная").setKey("isFluid")
                addColumn { row -> row.barcode ?: "-" }.setHeader("Штрихкод").setKey("barcode")
                
                // Колонка действий
                addColumn(ComponentRenderer<Button, StudyRow> { row ->
                    Button("Просмотр") { viewStudyDetails(row) }.apply {
                        addThemeVariants(ButtonVariant.LUMO_TERTIARY)
                        className = "button-small"
                    }
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
                    addColumn { row -> row.id }.setHeader("ID")
                    addColumn { row -> row.studyDate }.setHeader("Дата")
                    addColumn { row -> row.labTechnician }.setHeader("Лаборант")
                }
                
                add(overviewGrid)
                
                val closeBtn = Button("Закрыть") { close() }
                add(closeBtn)
            }
            
            add(content)
        }
        
        // Модальное окно поиска пациента
        patientSearchDialog.apply {
            width = "600px"
            
            val content = VerticalLayout().apply {
                setPadding(true)
                setSpacing(true)
                
                add(H2("Поиск пациента"))
                
                val searchField = TextField("ФИО")
                val searchBtn = Button("Найти")
                val resultsList = ListBox<String>()
                
                searchBtn.addClickListener {
                    ioScope.launch {
                        try {
                            progressBar.isVisible = true
                            val patients = patientRepository.findByFio(searchField.value)
                            
                            uiScope.launch {
                                resultsList.items = patients.map { "${it.lastName} ${it.firstName} ${it.middleName}" }
                                progressBar.isVisible = false
                            }
                        } catch (e: Exception) {
                            uiScope.launch {
                                Notification.show("Ошибка поиска: ${e.message}", 3000, Notification.Position.BOTTOM_CENTER)
                                progressBar.isVisible = false
                            }
                        }
                    }
                }
                
                add(searchField, searchBtn, resultsList)
                
                val closeBtn = Button("Закрыть") { close() }
                add(closeBtn)
            }
            
            add(content)
        }
        
        // Модальное окно деталей исследования
        studyDetailsDialog.apply {
            width = "800px"
            
            val content = VerticalLayout().apply {
                setPadding(true)
                setSpacing(true)
                
                add(H2("Детали исследования"))
                
                val detailsText = Paragraph()
                add(detailsText)
                
                val closeBtn = Button("Закрыть") { close() }
                add(closeBtn)
            }
            
            add(content)
        }
    }

    private fun setupOverviewFilters(): HorizontalLayout {
        return HorizontalLayout().apply {
            setWidthFull()
            isSpacing = true
            
            val dateFrom = DatePicker("С даты")
            val dateTo = DatePicker("По дату")
            val doctorFilter = ComboBox<String>("Врач").apply {
                setItems(emptyList())
            }
            
            add(dateFrom, dateTo, doctorFilter)
        }
    }

    private fun loadData() {
        ioScope.launch {
            try {
                progressBar.isVisible = true
                
                // Загрузка справочников
                val doctors = userRepository.findAllDoctors()
                val organizations = patientRepository.findAllOrganizations()
                val departments = patientRepository.findAllDepartments()
                
                uiScope.launch {
                    doctorComboBox.setItems(doctors)
                    referringDoctorComboBox.setItems(doctors)
                    medicalOrganizationComboBox.setItems(organizations)
                    departmentComboBox.setItems(departments)
                    
                    loadStudies()
                    progressBar.isVisible = false
                }
            } catch (e: Exception) {
                uiScope.launch {
                    Notification.show("Ошибка загрузки данных: ${e.message}", 3000, Notification.Position.BOTTOM_CENTER)
                    progressBar.isVisible = false
                }
            }
        }
    }

    private fun loadStudies() {
        ioScope.launch {
            try {
                val studies = studyRepository.findAll()
                
                uiScope.launch {
                    val rows = studies.map { study ->
                        StudyRow(
                            id = study.id,
                            studyDate = study.studyDate?.toString() ?: "",
                            labTechnician = study.labTechnician ?: "",
                            isFluid = study.isFluid ?: false,
                            barcode = study.barcode
                        )
                    }
                    studiesGrid.setItems(rows)
                }
            } catch (e: Exception) {
                uiScope.launch {
                    Notification.show("Ошибка загрузки исследований: ${e.message}", 3000, Notification.Position.BOTTOM_CENTER)
                }
            }
        }
    }

    private fun calculateAge() {
        birthDateField.value?.let { birthDate ->
            val age = Period.between(birthDate, LocalDate.now()).years
            ageField.value = age.toString()
        }
    }

    private fun createNewStudy() {
        clearForm()
        Notification.show("Создание нового исследования", 2000, Notification.Position.BOTTOM_CENTER)
    }

    private fun clearForm() {
        caseNumberField.clear()
        ambulatorySearchField.clear()
        directionField.clear()
        peresmotrCheckbox.value = false
        patientLastNameField.clear()
        patientFirstNameField.clear()
        patientMiddleNameField.clear()
        birthDateField.clear()
        ageField.clear()
        snilsField.clear()
        addressField.clear()
        insuranceField.clear()
        isDismissedField.clear()
        ambulatoryCardNumberField.clear()
        isEmployedCheckbox.value = false
        directionNumberField.clear()
        receiptDateField.clear()
        slidesCountField.clear()
        studyDateField.clear()
        conclusionTextArea.clear()
    }

    private fun printReferral() {
        Notification.show("Печать направления", 2000, Notification.Position.BOTTOM_CENTER)
    }

    private fun showStudiesOverview() {
        studiesOverviewDialog.open()
    }

    private fun showProfilaktika() {
        Notification.show("Профосмотр", 2000, Notification.Position.BOTTOM_CENTER)
    }

    private fun showReports() {
        Notification.show("Отчеты", 2000, Notification.Position.BOTTOM_CENTER)
    }

    private fun logout() {
        VaadinSession.getCurrent().session.invalidate()
        UI.getCurrent().navigate("login")
    }

    private fun showPatientSearch() {
        patientSearchDialog.open()
    }

    private fun saveStudy() {
        ioScope.launch {
            try {
                progressBar.isVisible = true
                
                // Сохранение исследования
                studyRepository.save(
                    caseNumber = caseNumberField.value,
                    patientFio = "${patientLastNameField.value} ${patientFirstNameField.value} ${patientMiddleNameField.value}",
                    studyDate = studyDateField.value,
                    conclusion = conclusionTextArea.value
                )
                
                uiScope.launch {
                    Notification.show("Исследование сохранено", 2000, Notification.Position.BOTTOM_CENTER)
                    progressBar.isVisible = false
                    loadStudies()
                }
            } catch (e: Exception) {
                uiScope.launch {
                    Notification.show("Ошибка сохранения: ${e.message}", 3000, Notification.Position.BOTTOM_CENTER)
                    progressBar.isVisible = false
                }
            }
        }
    }

    private fun viewStudyDetails(row: StudyRow) {
        studyDetailsDialog.open()
    }

    private fun editStudy(row: StudyRow) {
        Notification.show("Редактирование исследования ${row.id}", 2000, Notification.Position.BOTTOM_CENTER)
    }

    private fun deleteStudy(row: StudyRow) {
        ioScope.launch {
            try {
                progressBar.isVisible = true
                studyRepository.deleteById(row.id)
                
                uiScope.launch {
                    Notification.show("Исследование удалено", 2000, Notification.Position.BOTTOM_CENTER)
                    progressBar.isVisible = false
                    loadStudies()
                }
            } catch (e: Exception) {
                uiScope.launch {
                    Notification.show("Ошибка удаления: ${e.message}", 3000, Notification.Position.BOTTOM_CENTER)
                    progressBar.isVisible = false
                }
            }
        }
    }

    override fun beforeEnter(event: BeforeEnterEvent) {
        val session = VaadinSession.getCurrent()
        val user = session.getAttribute("user")
        if (user == null) {
            event.forwardTo("login")
        }
    }
}
