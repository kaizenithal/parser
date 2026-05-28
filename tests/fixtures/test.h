#ifndef USER_SERVICE_H
#define USER_SERVICE_H

#include <stddef.h>
#include "types.h"

/* ── Enum ────────────────────────────────────────────────────────── */

typedef enum {
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_PENDING,
} Status;

/* ── Struct ──────────────────────────────────────────────────────── */

typedef struct {
    char id[16];
    char name[64];
    char email[128];
    Status status;
} UserRecord;

typedef struct {
    UserRecord* users;
    size_t count;
    size_t capacity;
} UserList;

/* ── Function declarations ───────────────────────────────────────── */

UserList* user_list_create(size_t initial_capacity);
UserRecord* find_user_by_id(const UserList* list, const char* id);
int create_user(UserList* list, const char* name, const char* email);
int validate_email(const char* email);
void free_user_list(UserList* list);

#endif /* USER_SERVICE_H */