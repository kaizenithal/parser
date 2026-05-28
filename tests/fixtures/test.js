import { Injectable, Logger } from '@nestjs/common';
import { UserRepository } from '../repositories/user.repository';

// ── Declarations ──────────────────────────────────────────────────

const MAX_RETRIES = 3;
let defaultTimeout = 5000;

// ── Base class ────────────────────────────────────────────────────

class BaseService {
  constructor(context) {
    this.logger = new Logger(context);
  }

  getServiceName() {
    return this.constructor.name;
  }
}

// ── Main class with inheritance ───────────────────────────────────

class UserService extends BaseService {
  #repository;
  #retryCount = 0;

  constructor(repository) {
    super('UserService');
    this.#repository = repository;
  }

  serialize() {
    return JSON.stringify({ service: this.getServiceName() });
  }

  async findById(id) {
    this.logger.log(`Finding user ${id}`);
    return this.#repository.findOne(id);
  }

  async createUser(input) {
    validateEmail(input.email);
    const user = await this.#repository.create(input);
    this.logger.log(`Created user ${user.id}`);
    return user;
  }

  #handleError(error) {
    this.#retryCount++;
    this.logger.error(error.message);
    if (this.#retryCount >= MAX_RETRIES) {
      throw error;
    }
  }
}

// ── Standalone function ───────────────────────────────────────────

function validateEmail(email) {
  const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return pattern.test(email);
}

// ── Async standalone function ─────────────────────────────────────

async function retryWithBackoff(fn, retries) {
  for (let i = 0; i < retries; i++) {
    try {
      await fn();
      return;
    } catch (err) {
      await sleep(Math.pow(2, i) * 1000);
    }
  }
}

// ── Arrow function assigned to const ──────────────────────────────

const formatUser = (user) => {
  return `${user.name} <${user.email}>`;
};

const sleep = (ms) => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

// ── Default export ────────────────────────────────────────────────

export default UserService;
export { validateEmail, formatUser };