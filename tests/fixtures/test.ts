import { Injectable, Logger } from '@nestjs/common';
import { UserRepository } from '../repositories/user.repository';
import type { Config } from './config';

// ── Declarations ──────────────────────────────────────────────────

const MAX_RETRIES: number = 3;
let defaultTimeout = 5000;

// ── Type alias ────────────────────────────────────────────────────

type UserRole = 'admin' | 'editor' | 'viewer';

type CreateUserInput = {
  name: string;
  email: string;
  role: UserRole;
};

// ── Enum ──────────────────────────────────────────────────────────

enum Status {
  Active = 'ACTIVE',
  Inactive = 'INACTIVE',
  Pending = 'PENDING',
}

// ── Interface ─────────────────────────────────────────────────────

interface Serializable {
  serialize(): string;
}

interface UserRecord extends Serializable {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: Status;
}

// ── Base class ────────────────────────────────────────────────────

class BaseService {
  protected logger: Logger;

  constructor(context: string) {
    this.logger = new Logger(context);
  }

  getServiceName(): string {
    return this.constructor.name;
  }
}

// ── Main class with inheritance and interface ─────────────────────

@Injectable()
class UserService extends BaseService implements Serializable {
  private repository: UserRepository;
  private retryCount: number = 0;

  constructor(repository: UserRepository) {
    super('UserService');
    this.repository = repository;
  }

  serialize(): string {
    return JSON.stringify({ service: this.getServiceName() });
  }

  async findById(id: string): Promise<UserRecord | null> {
    this.logger.log(`Finding user ${id}`);
    return this.repository.findOne(id);
  }

  async createUser(input: CreateUserInput): Promise<UserRecord> {
    validateEmail(input.email);
    const user = await this.repository.create(input);
    this.logger.log(`Created user ${user.id}`);
    return user;
  }

  @Logger.timed()
  override getServiceName(): string {
    return `UserService:v2`;
  }

  private handleError(error: Error): void {
    this.retryCount++;
    this.logger.error(error.message);
    if (this.retryCount >= MAX_RETRIES) {
      throw error;
    }
  }
}

// ── Standalone function ───────────────────────────────────────────

function validateEmail(email: string): boolean {
  const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return pattern.test(email);
}

// ── Async standalone function ─────────────────────────────────────

async function retryWithBackoff(
  fn: () => Promise<void>,
  retries: number,
): Promise<void> {
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

const formatUser = (user: UserRecord): string => {
  return `${user.name} <${user.email}>`;
};

const sleep = (ms: number): Promise<void> => {
  return new Promise(resolve => setTimeout(resolve, ms));
};

// ── Default export ────────────────────────────────────────────────

export default UserService;
export { validateEmail, formatUser };