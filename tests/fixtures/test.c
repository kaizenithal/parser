#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "user_repository.h"

/* ── Constants ───────────────────────────────────────────────────── */

#define MAX_RETRIES 3
#define MAX_NAME_LEN 64
#define MAX_EMAIL_LEN 128

static const int DEFAULT_TIMEOUT = 5000;

/* ── Enum ────────────────────────────────────────────────────────── */

typedef enum {
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_PENDING,
} Status;

/* ── Struct ──────────────────────────────────────────────────────── */

typedef struct {
    char id[16];
    char name[MAX_NAME_LEN];
    char email[MAX_EMAIL_LEN];
    Status status;
} UserRecord;

typedef struct {
    UserRecord* users;
    size_t count;
    size_t capacity;
} UserList;

/* ── Function declarations ───────────────────────────────────────── */

UserRecord* find_user_by_id(const UserList* list, const char* id);
int create_user(UserList* list, const char* name, const char* email);
int validate_email(const char* email);
void free_user_list(UserList* list);

/* ── Function implementations ────────────────────────────────────── */

UserList* user_list_create(size_t initial_capacity) {
    UserList* list = malloc(sizeof(UserList));
    if (!list) return NULL;

    list->users = malloc(sizeof(UserRecord) * initial_capacity);
    if (!list->users) {
        free(list);
        return NULL;
    }

    list->count = 0;
    list->capacity = initial_capacity;
    return list;
}

UserRecord* find_user_by_id(const UserList* list, const char* id) {
    for (size_t i = 0; i < list->count; i++) {
        if (strcmp(list->users[i].id, id) == 0) {
            return &list->users[i];
        }
    }
    return NULL;
}

int create_user(UserList* list, const char* name, const char* email) {
    if (!validate_email(email)) {
        fprintf(stderr, "Invalid email: %s\n", email);
        return -1;
    }

    if (list->count >= list->capacity) {
        size_t new_capacity = list->capacity * 2;
        UserRecord* new_users = realloc(list->users,
            sizeof(UserRecord) * new_capacity);
        if (!new_users) return -1;
        list->users = new_users;
        list->capacity = new_capacity;
    }

    UserRecord* user = &list->users[list->count];
    snprintf(user->id, sizeof(user->id), "USR%05zu", list->count);
    strncpy(user->name, name, MAX_NAME_LEN - 1);
    user->name[MAX_NAME_LEN - 1] = '\0';
    strncpy(user->email, email, MAX_EMAIL_LEN - 1);
    user->email[MAX_EMAIL_LEN - 1] = '\0';
    user->status = STATUS_ACTIVE;

    list->count++;
    printf("Created user %s\n", user->id);
    return 0;
}

int validate_email(const char* email) {
    if (!email) return 0;
    const char* at = strchr(email, '@');
    if (!at) return 0;
    if (at == email) return 0;
    if (*(at + 1) == '\0') return 0;
    return 1;
}

void free_user_list(UserList* list) {
    if (!list) return;
    free(list->users);
    free(list);
}

/* ── Main ────────────────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    UserList* users = user_list_create(16);
    if (!users) {
        fprintf(stderr, "Failed to create user list\n");
        return 1;
    }

    create_user(users, "Alice Smith", "alice@example.com");
    create_user(users, "Bob Jones", "bob@example.com");

    UserRecord* found = find_user_by_id(users, "USR00000");
    if (found) {
        printf("Found: %s <%s>\n", found->name, found->email);
    }

    free_user_list(users);
    return 0;
}