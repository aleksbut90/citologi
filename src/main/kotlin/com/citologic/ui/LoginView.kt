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
@CssImport("./styles/login-styles.css")
class LoginView(
    private val authenticationManager: AuthenticationManager,
    private val userDetailsService: CustomUserDetailsService
) : VerticalLayout(), BeforeEnterObserver {

    private val usernameField = TextField("Логин").apply {
        width = "100%"
        placeholder = "Введите логин"
    }

    private val passwordField = PasswordField("Пароль").apply {
        width = "100%"
        placeholder = "Введите пароль"
    }

    private val rememberMeCheckbox = Checkbox("Запомнить меня").apply {
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

    init {
        setSizeFull()
        justifyContentMode = FlexComponent.JustifyContentMode.CENTER
        alignItems = Alignment.CENTER
        addClassName("login-page")

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

        add(loginContainer)
    }

    private fun handleLogin() {
        val username = usernameField.value.trim()
        val password = passwordField.value

        if (username.isEmpty() || password.isEmpty()) {
            showError("Пожалуйста, заполните все поля")
            return
        }

        if (password.length < 6) {
            showError("Пароль должен содержать минимум 6 символов")
            return
        }

        if (!Regex("^[a-zA-Z0-9_]+$").matches(username)) {
            showError("Логин может содержать только буквы, цифры и знак подчеркивания")
            return
        }

        setLoading(true)

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
            showError("Неверный логин или пароль")
            setLoading(false)
        }
    }

    private fun showError(message: String) {
        errorAlert.text = message
        errorAlert.isVisible = true
        Notification.show(message, 5000, Notification.Position.TOP_CENTER)
    }

    private fun setLoading(loading: Boolean) {
        loginSpinner.isVisible = loading
        loginButton.isEnabled = !loading
        usernameField.isEnabled = !loading
        passwordField.isEnabled = !loading
    }

    override fun beforeEnter(event: BeforeEnterEvent) {
        val auth = SecurityContextHolder.getContext().authentication

        if (auth != null &&
            auth.isAuthenticated &&
            auth !is org.springframework.security.authentication.AnonymousAuthenticationToken
        ) {
            event.rerouteTo("/")
        }
    }
}
