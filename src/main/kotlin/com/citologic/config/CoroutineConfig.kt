package com.citologic.config

import kotlinx.coroutines.*
import org.springframework.stereotype.Component
import java.util.concurrent.Executors
import kotlin.coroutines.CoroutineContext

@Component
class CoroutineConfig {
    
    // Основной скоуп для UI операций (выполняется в Dispatchers.Main)
    val uiScope: CoroutineScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    
    // Скоуп для фоновых операций с БД (выполняется в Dispatchers.IO)
    val ioScope: CoroutineScope = CoroutineScope(
        Dispatchers.IO + SupervisorJob() + 
        CoroutineName("DB-Operations")
    )
    
    // Скоуп для тяжелых вычислений
    val defaultScope: CoroutineScope = CoroutineScope(
        Dispatchers.Default + SupervisorJob() + 
        CoroutineName("Default-Operations")
    )
}
