package com.citologic.config

import com.citologic.security.CustomAuthenticationProvider
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.core.annotation.Order
import org.springframework.security.authentication.AuthenticationManager
import org.springframework.security.authentication.ProviderManager
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer
import org.springframework.security.config.annotation.web.configurers.HeadersConfigurer
import org.springframework.security.web.SecurityFilterChain
import org.springframework.security.web.savedrequest.HttpSessionRequestCache
import org.springframework.security.web.util.matcher.RegexRequestMatcher

@Configuration
@EnableWebSecurity
class SecurityConfig(
    private val authProvider: CustomAuthenticationProvider
) {

    @Bean
    fun authenticationManager(): AuthenticationManager {
        return ProviderManager(authProvider)
    }

    @Bean
    @Order(1)
    fun filterChain(http: HttpSecurity): SecurityFilterChain {
        http
            .headers { headers ->
                headers.frameOptions(HeadersConfigurer.FrameOptionsConfig::disable)
            }
            .csrf(AbstractHttpConfigurer::disable)
            .requestCache { cache ->
                val requestCache = HttpSessionRequestCache()
                requestCache.setMatchingRequestParameterName("continue")
                cache.requestCache(requestCache)
            }
            .authorizeHttpRequests { auth ->
                auth
                    .requestMatchers(RegexRequestMatcher("/VAADIN/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/frontend/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/webjars/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/icons/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/images/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/styles/.*", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/manifest.webmanifest", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/sw.js", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/offline.html", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/sw-runtime-resources-precache.js", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/favicon.ico", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/robots.txt", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/login", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/logout", null)).permitAll()
                    .requestMatchers(RegexRequestMatcher("/error", null)).permitAll()
                    .anyRequest().authenticated()
            }
            .formLogin { form ->
                form
                    .loginPage("/login")
                    .loginProcessingUrl("/login")
                    .defaultSuccessUrl("/", true)
                    .permitAll()
            }
            .logout { logout ->
                logout
                    .logoutUrl("/logout")
                    .logoutSuccessUrl("/login?logout")
                    .invalidateHttpSession(true)
                    .deleteCookies("JSESSIONID")
                    .permitAll()
            }

        return http.build()
    }
}
