package com.citologic.ui.components

import com.vaadin.flow.component.html.Div
import com.vaadin.flow.component.progressbar.ProgressBar
import com.vaadin.flow.component.orderedlayout.VerticalLayout
import com.vaadin.flow.component.html.Span
import com.vaadin.flow.component.orderedlayout.FlexComponent

/**
 * Кастомный компонент прогресс-бара с текстовым сообщением
 */
class CustomProgressBar : VerticalLayout() {
    
    private val progressBar = ProgressBar().apply {
        isIndeterminate = true
        width = "100%"
    }
    
    private val statusLabel = Span("Загрузка данных...").apply {
        addClassName("status-label")
    }
    
    init {
        setAlignItems(FlexComponent.Alignment.CENTER)
        setJustifyContentMode(FlexComponent.JustifyContentMode.CENTER)
        setPadding(true)
        setSpacing(true)
        
        add(progressBar, statusLabel)
        isVisible = false
        
        // Стили
        addClassName("custom-progress-bar")
        setWidthFull()
    }
    
    fun show(message: String = "Загрузка данных...") {
        statusLabel.text = message
        isVisible = true
    }
    
    fun hide() {
        isVisible = false
    }
    
    fun updateMessage(message: String) {
        if (statusLabel.text != message) {
            statusLabel.text = message
        }
    }
}
