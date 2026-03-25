package com.citologic

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class CitologiApplication

fun main(args: Array<String>) {
    runApplication<CitologiApplication>(*args)
}
