#include <string>
#include <vector>
#include <memory>
#include <stdexcept>
#include "user_repository.h"
#include "logger.h"

// ── Constants ─────────────────────────────────────────────────────

const int MAX_RETRIES = 3;
static const std::string DEFAULT_ROLE = "viewer";

// ── Enum ──────────────────────────────────────────────────────────

enum class Status {
    Active,
    Inactive,
    Pending,
};

// ── Struct ────────────────────────────────────────────────────────

struct UserRecord {
    std::string id;
    std::string name;
    std::string email;
    Status status;
};

// ── Forward declaration ───────────────────────────────────────────

class UserService;

// ── Base class ────────────────────────────────────────────────────

class BaseService {
protected:
    Logger logger;

public:
    explicit BaseService(const std::string& context)
        : logger(context) {}

    virtual ~BaseService() = default;

    virtual std::string getServiceName() const {
        return "BaseService";
    }

    void logInfo(const std::string& message) const {
        logger.log(message);
    }
};

// ── Interface-like abstract class ─────────────────────────────────

class Serializable {
public:
    virtual ~Serializable() = default;
    virtual std::string serialize() const = 0;
};

// ── Template function ─────────────────────────────────────────────

template<typename T>
std::vector<T> filterByStatus(const std::vector<T>& items, Status status) {
    std::vector<T> result;
    for (const auto& item : items) {
        if (item.status == status) {
            result.push_back(item);
        }
    }
    return result;
}

// ── Main class with multiple inheritance ──────────────────────────

class UserService : public BaseService, public Serializable {
private:
    std::unique_ptr<UserRepository> repository;
    int retryCount;

public:
    explicit UserService(std::unique_ptr<UserRepository> repo)
        : BaseService("UserService")
        , repository(std::move(repo))
        , retryCount(0) {}

    std::string serialize() const override {
        return "{\"service\": \"" + getServiceName() + "\"}";
    }

    std::string getServiceName() const override {
        return "UserService:v2";
    }

    UserRecord findById(const std::string& id) const {
        logInfo("Finding user " + id);
        return repository->findOne(id);
    }

    UserRecord createUser(const std::string& name, const std::string& email) {
        validateEmail(email);
        auto user = repository->create(name, email);
        logInfo("Created user " + user.id);
        return user;
    }

private:
    void handleError(const std::exception& error) {
        retryCount++;
        logger.error(error.what());
        if (retryCount >= MAX_RETRIES) {
            throw error;
        }
    }
};

// ── Standalone function ───────────────────────────────────────────

bool validateEmail(const std::string& email) {
    return email.find('@') != std::string::npos;
}

// ── Namespace ─────────────────────────────────────────────────────

namespace utils {

std::string formatUser(const UserRecord& user) {
    return user.name + " <" + user.email + ">";
}

int clamp(int value, int low, int high) {
    if (value < low) return low;
    if (value > high) return high;
    return value;
}

} // namespace utils