package com.example.service

import com.example.model.User
import com.example.repo.UserRepository
import org.springframework.stereotype.Service
import kotlinx.coroutines.flow.Flow

interface Auditable {
    fun getAuditLog(): List<String>
}

@Service
data class AppConfig(
    val baseUrl: String,
    val maxRetries: Int = 3,
)

@Service
class UserService(
    private val repo: UserRepository,
    private val config: AppConfig,
) : BaseService(), Auditable {

    companion object {
        private val log by LoggerDelegate()
        const val DEFAULT_PAGE_SIZE = 20
    }

    override fun getAuditLog(): List<String> {
        return repo.findAuditEntries()
    }

    fun findUser(id: Long): User? {
        log.info("Finding user: $id")
        return repo.findById(id)
    }

    fun createUser(name: String, email: String): User {
        val user = User(name = name, email = email)
        repo.save(user)
        return user
    }

    suspend fun fetchRemoteProfile(userId: Long): UserProfile {
        val response = httpClient.get("${config.baseUrl}/users/$userId")
        return response.body()
    }

    class UserNotFoundException(
        val userId: Long,
    ) : RuntimeException("User not found: $userId")
}

object Registry {
    private val services = mutableMapOf<String, Any>()

    fun register(name: String, service: Any) {
        services[name] = service
    }

    fun lookup(name: String): Any? {
        return services[name]
    }
}

val DEFAULT_TIMEOUT: Long = 30_000L