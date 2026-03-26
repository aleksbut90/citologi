package com.citologic.ui.components

import com.vaadin.flow.component.html.Div

/**
 * Простой компонент Card для группировки контента
 */
class Card : Div() {
    init {
        addClassName("card")
        style.set("border", "1px solid var(--lumo-contrast-20pct)")
        style.set("border-radius", "var(--lumo-border-radius-m)")
        style.set("padding", "var(--lumo-space-m)")
        style.set("background-color", "var(--lumo-base-color)")
        style.set("box-shadow", "var(--lumo-box-shadow-s)")
    }
}
