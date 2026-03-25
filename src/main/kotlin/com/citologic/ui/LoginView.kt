package com.citologic.ui

import com.citologic.service.CustomUserDetailsService
import com.vaadin.flow.component.*
import com.vaadin.flow.component.button.Button
import com.vaadin.flow.component.button.ButtonVariant
import com.vaadin.flow.component.checkbox.Checkbox
import com.vaadin.flow.component.dependency.CssImport
import com.vaadin.flow.component.html.*
import com.vaadin.flow.component.icon.Icon
import com.vaadin.flow.component.icon.VaadinIcon
import com.vaadin.flow.component.notification.Notification
import com.vaadin.flow.component.orderedlayout.FlexComponent
import com.vaadin.flow.component.orderedlayout.FlexComponent.Alignment
import com.vaadin.flow.component.orderedlayout.HorizontalLayout
import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.component.textfield.PasswordField
import com.vaadin.flow.component.textfield.TextField
import com.vaadin.flow.router.BeforeEnterEvent
import com.vaadin.flow.router.BeforeEnterObserver
import com.vaadin.flow.router.Route
import com.vaadin.flow.server.VaadinSession
import com.vaadin.flow.server.auth.AnonymousAllowed
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken
import org.springframework.security.core.context.SecurityContextHolder
import org.springframework.security.web.context.HttpSessionSecurityContextRepository
import java.time.LocalDateTime

@Route("login")
@AnonymousAllowed
@CssImport(value = "./styles/login-styles.css", themeFor = "vaadin-login-form")
class LoginView : VerticalLayout(), BeforeEnterObserver {

    @Autowired
    private lateinit var authenticationManager: AuthenticationManager

    @Autowired
    private lateinit var userDetailsService: CustomUserDetailsService

    private val usernameField = TextField("Логин").apply {
        width = "100%"
        placeholder = "Введите логин"
        setThemeName("large")
    }

    private val passwordField = PasswordField("Пароль").apply {
        width = "100%"
        placeholder = "Введите пароль"
        setThemeName("large")
    }

    private val rememberMeCheckbox = Checkbox("Запомнить меня").apply {
        setThemeName("small")
    }

    private val loginButton = Button("Войти").apply {
        width = "100%"
        addThemeVariants(ButtonVariant.LUMO_PRIMARY, ButtonVariant.LUMO_LARGE)
        addClickListener { handleLogin() }
    }

    private val errorAlert = Div().apply {
        isVisible = false
        addClassName("error-alert")
        val icon = Icon(VaadinIcon.EXCLAMATION_CIRCLE_O)
        val messageSpan = Span()
        messageSpan.element.setAttribute("id", "errorMessage")
        add(icon, messageSpan)
    }

    private val loginSpinner = Div().apply {
        isVisible = false
        addClassName("loading-spinner")
    }

    // Admin modal components
    private val adminModal = Div().apply {
        addClassName("admin-modal")
        isVisible = false
    }

    private val adminUsernameField = TextField("Логин").apply {
        width = "100%"
        placeholder = "Введите логин администратора"
        setThemeName("large")
    }

    private val adminPasswordField = PasswordField("Пароль").apply {
        width = "100%"
        placeholder = "Введите пароль администратора"
        setThemeName("large")
    }

    private val adminErrorAlert = Div().apply {
        isVisible = false
        addClassName("error-alert")
        val icon = Icon(VaadinIcon.EXCLAMATION_CIRCLE_O)
        val messageSpan = Span()
        messageSpan.element.setAttribute("id", "adminErrorMessage")
        add(icon, messageSpan)
    }

    private val adminLoginButton = Button("Войти").apply {
        width = "100%"
        addThemeVariants(ButtonVariant.LUMO_PRIMARY, ButtonVariant.LUMO_LARGE)
        addClickListener { handleAdminLogin() }
    }

    private val adminLoginSpinner = Div().apply {
        isVisible = false
        addClassName("loading-spinner")
    }

    init {
        setSizeFull()
        justifyContentMode = FlexComponent.JustifyContentMode.CENTER
        alignItems(Alignment.CENTER)
        addClassName("login-page")

        // Admin settings icon
        val adminSettingsIcon = Icon(VaadinIcon.COG).apply {
            addClassName("admin-settings")
            addClickListener { 
                adminModal.isVisible = true
                adminErrorAlert.isVisible = false
            }
        }

        // Login container
        val loginContainer = VerticalLayout().apply {
            addClassName("login-container")
            setPadding(true)
            width = "400px"
            maxWidth = "100%"

            // Header with logo placeholder
            val headerDiv = Div().apply {
                addClassName("login-header")
                style.set("text-align", "center")
                
                val logoPlaceholder = Div().apply {
                    addClassName("logo-placeholder")
                    text = "🔬"
                    style.set("font-size", "80px")
                }
                
                val title = H2("Вход в систему").apply {
                    style.set("margin-top", "1rem")
                    style.set("margin-bottom", "0.5rem")
                }
                
                val subtitle = Paragraph("Система учета цитологических исследований").apply {
                    addClassName("text-muted")
                    style.set("margin-top", "0")
                }

                add(logoPlaceholder, title, subtitle)
            }

            val formLayout = VerticalLayout().apply {
                setPadding(false)
                isSpacing = false
                width = "100%"

                add(usernameField)
                add(passwordField)
                add(rememberMeCheckbox)
                add(errorAlert)
                
                val buttonWrapper = HorizontalLayout(loginButton).apply {
                    width = "100%"
                    justifyContentMode = FlexComponent.JustifyContentMode.CENTER
                    style.set("margin-top", "1rem")
                }
                add(buttonWrapper)
            }

            add(headerDiv, formLayout)

            // Footer
            val footer = Div().apply {
                addClassName("login-footer")
                style.set("text-align", "center")
                style.set("margin-top", "2rem")
                style.set("font-size", "0.9rem")
                style.set("color", "#6c757d")
                text = "Версия 1.0.0"
            }
            add(footer)
        }

        // Admin modal content
        val adminModalContent = Div().apply {
            addClassName("admin-modal-content")
            
            val closeIcon = Icon(VaadinIcon.CLOSE).apply {
                addClassName("close-admin-modal")
                addClickListener { adminModal.isVisible = false }
            }

            val adminHeader = H2("Вход для администратора").apply {
                style.set("text-align", "center")
                style.set("margin-bottom", "1.5rem")
            }

            val adminForm = VerticalLayout().apply {
                setPadding(false)
                isSpacing = false
                width = "100%"

                add(adminUsernameField)
                add(adminPasswordField)
                add(adminErrorAlert)
                
                val adminButtonWrapper = HorizontalLayout(adminLoginButton).apply {
                    width = "100%"
                    justifyContentMode = FlexComponent.JustifyContentMode.CENTER
                    style.set("margin-top", "1rem")
                }
                add(adminButtonWrapper)
            }

            add(closeIcon, adminHeader, adminForm)
        }

        adminModal.add(adminModalContent)

        add(adminSettingsIcon, loginContainer, adminModal)
    }

    private fun handleLogin() {
        val username = usernameField.value.trim()
        val password = passwordField.value

        if (username.isEmpty() || password.isEmpty()) {
            showError("Пожалуйста, заполните все поля", false)
            return
        }

        if (password.length < 6) {
            showError("Пароль должен содержать минимум 6 символов", false)
            return
        }

        if (!Regex("^[a-zA-Z0-9_]+$").matches(username)) {
            showError("Логин может содержать только буквы, цифры и знак подчеркивания", false)
            return
        }

        setLoading(true, false)

        try {
            val authentication = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken(username, password)
            )

            SecurityContextHolder.getContext().authentication = authentication
            
            val session = VaadinSession.getCurrent()
            session.session.setAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
                SecurityContextHolder.getContext()
            )

            // Handle remember me
            if (rememberMeCheckbox.value) {
                session.session.maxInactiveInterval = 7 * 24 * 60 * 60 // 7 days
            }

            // Get user details and redirect based on role
            val userDetails = userDetailsService.loadUserByUsername(username)
            val role = userDetails.authorities.firstOrNull()?.authority?.removePrefix("ROLE_") ?: "USER"

            // Store user info in session
            session.setAttribute("userFIO", username) // Can be extended with actual FIO
            session.setAttribute("userStatus", role)
            session.setAttribute("isAdmin", role == "admin")

            // Redirect based on role
            if (role == "admin") {
                UI.getCurrent().page.setLocation("/admin")
            } else {
                UI.getCurrent().page.setLocation("/")
            }

        } catch (e: Exception) {
            showError("Неверный логин или пароль", false)
            setLoading(false, false)
        }
    }

    private fun handleAdminLogin() {
        val username = adminUsernameField.value.trim()
        val password = adminPasswordField.value

        if (username.isEmpty() || password.isEmpty()) {
            showAdminError("Пожалуйста, заполните все поля")
            return
        }

        setAdminLoading(true)

        try {
            val authentication = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken(username, password)
            )

            SecurityContextHolder.getContext().authentication = authentication

            val userDetails = userDetailsService.loadUserByUsername(username)
            val role = userDetails.authorities.firstOrNull()?.authority?.removePrefix("ROLE_") ?: "USER"

            if (role != "admin") {
                showAdminError("Требуется права администратора")
                setAdminLoading(false)
                return
            }

            val session = VaadinSession.getCurrent()
            session.session.setAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
                SecurityContextHolder.getContext()
            )
            session.setAttribute("userFIO", username)
            session.setAttribute("userStatus", role)
            session.setAttribute("isAdmin", true)

            adminModal.isVisible = false
            UI.getCurrent().page.setLocation("/admin")

        } catch (e: Exception) {
            showAdminError("Неверный логин или пароль администратора")
            setAdminLoading(false)
        }
    }

    private fun showError(message: String, isAdmin: Boolean) {
        if (isAdmin) {
            showAdminError(message)
        } else {
            errorAlert.text = message
            errorAlert.isVisible = true
            Notification.show(message, 5000, Notification.Position.TOP_CENTER)
        }
    }

    private fun showAdminError(message: String) {
        adminErrorAlert.text = message
        adminErrorAlert.isVisible = true
    }

    private fun setLoading(loading: Boolean, isAdmin: Boolean) {
        loginSpinner.isVisible = loading
        loginButton.isEnabled = !loading
        usernameField.isEnabled = !loading
        passwordField.isEnabled = !loading
    }

    private fun setAdminLoading(loading: Boolean) {
        adminLoginSpinner.isVisible = loading
        adminLoginButton.isEnabled = !loading
        adminUsernameField.isEnabled = !loading
        adminPasswordField.isEnabled = !loading
    }

    override fun beforeEnter(event: BeforeEnterEvent) {
        // Check if already logged in
        val auth = SecurityContextHolder.getContext().authentication
        if (auth != null && auth.isAuthenticated && auth.principal != "anonymousUser") {
            event.rerouteTo("/")
        }
    }
}
