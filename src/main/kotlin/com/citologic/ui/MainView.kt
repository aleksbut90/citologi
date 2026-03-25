package com.citologic.ui

import com.vaadin.flow.component.UI
import com.vaadin.flow.component.button.Button
import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.router.Route

@Route("")
class MainView : VerticalLayout() {

    init {
        add("Добро пожаловать в систему Citologi!")
        
        val logoutBtn = Button("Выйти") {
            // Перенаправление на logout обрабатывается Spring Security
            UI.getCurrent().page.setLocation("logout")
        }
        add(logoutBtn)
    }
}
