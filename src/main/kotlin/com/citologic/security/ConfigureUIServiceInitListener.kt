package com.citologic.security

import com.citologic.ui.LoginView
import com.citologic.ui.MainView
import com.vaadin.flow.component.UI
import com.vaadin.flow.router.BeforeEnterEvent
import com.vaadin.flow.server.*
import com.vaadin.flow.server.communication.IndexHtmlRequestListener
import com.vaadin.flow.server.communication.IndexHtmlResponse
import org.springframework.stereotype.Component

@Component
class ConfigureUIServiceInitListener :
    VaadinServiceInitListener,
    IndexHtmlRequestListener {

    override fun serviceInit(event: ServiceInitEvent) {

        event.addIndexHtmlRequestListener(this)

        event.source.addUIInitListener { uiEvent ->
            val ui = uiEvent.ui
            ui.addBeforeEnterListener(this::authenticateNavigation)
        }
    }

    private fun authenticateNavigation(event: BeforeEnterEvent) {
        val loggedIn = SecurityUtils.isUserLoggedIn()
        val target = event.navigationTarget

        // Неавторизованный → только LoginView
        if (!loggedIn && target != LoginView::class.java) {
            event.rerouteTo(LoginView::class.java)
            return
        }

        // Авторизованный → не пускать на LoginView
        if (loggedIn && target == LoginView::class.java) {
            event.rerouteTo(MainView::class.java)
        }
    }

    override fun modifyIndexHtmlResponse(response: IndexHtmlResponse) {
        response.document.getElementsByTag("html").attr("lang", "ru")
    }
}
