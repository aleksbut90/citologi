package com.citologic.ui

import com.vaadin.flow.component.login.LoginForm
import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.router.Route
import com.vaadin.flow.server.auth.AnonymousAllowed

@Route("login")
@AnonymousAllowed
class LoginView : VerticalLayout() {

    init {
        setSizeFull()
        justifyContentMode = JustifyContentMode.CENTER
        alignItemsItems = Alignment.CENTER

        val loginForm = LoginForm()
        // Vaadin Spring Security автоматически обрабатывает POST на /login
        add(loginForm)
    }
}
