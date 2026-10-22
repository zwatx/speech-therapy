import { PGlite } from "@electric-sql/pglite";

import type { DatabaseClient, QueryResult } from "./database.ts";

export class PGliteDatabase implements DatabaseClient {
  readonly #database: PGlite;

  constructor(dataDirectory: string = "memory://") {
    this.#database = new PGlite(dataDirectory);
  }

  async query<Row extends Record<string, unknown>>(
    text: string,
    params: readonly unknown[] = [],
  ): Promise<QueryResult<Row>> {
    const result = await this.#database.query<Row>(text, [...params]);
    return { rows: result.rows };
  }

  async close(): Promise<void> {
    await this.#database.close();
  }

  async executeScript(sql: string): Promise<void> {
    await this.#database.exec(sql);
  }
}
