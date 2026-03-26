package com.citologic.security

import org.springframework.security.core.Authentication
import org.springframework.security.core.context.SecurityContextHolder
import org.springframework.security.authentication.AnonymousAuthenticationToken

object SecurityUtils {

    fun isUserLoggedIn(): Boolean {
        val auth: Authentication? = SecurityContextHolder.getContext().authentication
        return auth != null &&
                auth.isAuthenticated &&
                auth !is AnonymousAuthenticationToken
    }
}
