export interface QueryResult<Row extends Record<string, unknown>> {
  readonly rows: readonly Row[];
}

export interface DatabaseClient {
  query<Row extends Record<string, unknown>>(
    text: string,
    params?: readonly unknown[],
  ): Promise<QueryResult<Row>>;
}

export interface MigrationDatabaseClient extends DatabaseClient {
  executeScript(sql: string): Promise<void>;
}
