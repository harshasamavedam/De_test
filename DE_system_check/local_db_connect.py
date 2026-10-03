
from cassandra.cluster import Cluster


def main():
    cluster = Cluster(["127.0.0.1"], port=9042)
    try:
        session = cluster.connect("payments")
        print("Connected to Cassandra keyspace 'payments'.")
        rows = session.execute(
            "SELECT count(*) "
            "FROM orders_table LIMIT 5"
        )
        for row in rows:
            print(row)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
