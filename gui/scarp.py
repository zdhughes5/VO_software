def connect_to_db():
    try:
        connection = psycopg2.connect(
            dbname="telescope_db",
            user="zdhughes",
            password="your_password",
            host="localhost",
            port="5432"
        )
        cursor = connection.cursor()
        print("Connected to the database")
        return connection, cursor
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None, None

def close_db(connection, cursor):
    cursor.close()
    connection.close()
    print("Database connection closed")

def insert_run_data(cursor, connection):
    try:
        insert_query = """
        INSERT INTO runs (veritas_run_id, run_type, run_status, run_window, db_start_time, db_end_time, data_start_time, data_end_time, duration, telescope_mask, harvester_mask, source_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        run_data = (
            12345,  # veritas_run_id
            'observing',  # run_type
            'started',  # run_status
            4,  # run_window
            datetime.now(),  # db_start_time
            datetime.now() + timedelta(hours=1),  # db_end_time
            datetime.now(),  # data_start_time
            datetime.now() + timedelta(hours=1),  # data_end_time
            timedelta(hours=1),  # duration
            1,  # telescope_mask
            1,  # harvester_mask
            'source_123'  # source_id
        )
        cursor.execute(insert_query, run_data)
        connection.commit()
        print("Run data inserted successfully")
    except Exception as e:
        print(f"Error inserting run data: {e}")
        connection.rollback()

# Example usage
connection, cursor = connect_to_db()
if connection and cursor:
    insert_run_data(cursor, connection)
    close_db(connection, cursor)


    def check_VO_db_params_filled(self):
        return all([
            self.VO_db_params['veritas_run_id'],
            self.VO_db_params['run_type'],
            self.VO_db_params['run_status'],
            self.VO_db_params['run_window'],
            self.VO_db_params['db_start_time'],
            self.VO_db_params['db_end_time'],
            self.VO_db_params['data_start_time'],
            self.VO_db_params['data_end_time'],
            self.VO_db_params['duration'],
            self.VO_db_params['telescope_mask'],
            self.VO_db_params['harvester_mask'],
            self.VO_db_params['source_id']
        ])