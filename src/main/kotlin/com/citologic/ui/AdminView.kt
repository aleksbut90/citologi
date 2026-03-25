package com.citologic.ui

import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.router.Route
import com.vaadin.flow.server.auth.AnonymousAllowed

@Route("admin")
class AdminView : VerticalLayout() {

    init {
        add("Панель администратора")
        add("Доступ разрешен только для пользователей с ролью ADMIN")
    }
}
