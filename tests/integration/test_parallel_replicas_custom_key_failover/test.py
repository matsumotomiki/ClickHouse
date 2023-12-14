import pytest
from helpers.cluster import ClickHouseCluster

cluster = ClickHouseCluster(__file__)

node1 = cluster.add_instance(
    "n1", main_configs=["configs/remote_servers.xml"], with_zookeeper=True
)
node3 = cluster.add_instance(
    "n3", main_configs=["configs/remote_servers.xml"], with_zookeeper=True
)

nodes = [node1, node3]


@pytest.fixture(scope="module", autouse=True)
def start_cluster():
    try:
        cluster.start()
        yield cluster
    finally:
        cluster.shutdown()


def create_tables(cluster, table_name):
    node1.query(f"DROP TABLE IF EXISTS {table_name} SYNC")
    node3.query(f"DROP TABLE IF EXISTS {table_name} SYNC")

    node1.query(
        f"CREATE TABLE IF NOT EXISTS {table_name} (key Int64, value String) Engine=ReplicatedMergeTree('/test_parallel_replicas/shard1/{table_name}', 'r1') ORDER BY (key)"
    )
    node3.query(
        f"CREATE TABLE IF NOT EXISTS {table_name} (key Int64, value String) Engine=ReplicatedMergeTree('/test_parallel_replicas/shard1/{table_name}', 'r3') ORDER BY (key)"
    )

    # create distributed table
    node1.query(f"DROP TABLE IF EXISTS {table_name}_d SYNC")
    node1.query(
        f"""
            CREATE TABLE {table_name}_d AS {table_name}
            Engine=Distributed(
                {cluster},
                currentDatabase(),
                {table_name},
                key
            )
            """
    )

    # populate data
    node1.query(
        f"INSERT INTO {table_name} SELECT number % 4, number FROM numbers(1000)"
    )
    node3.query(
        f"INSERT INTO {table_name} SELECT number % 4, number FROM numbers(1000, 1000)"
    )
    node1.query(f"SYSTEM SYNC REPLICA {table_name}")
    node3.query(f"SYSTEM SYNC REPLICA {table_name}")


@pytest.mark.parametrize("use_hedged_requests", [1, 0])
@pytest.mark.parametrize("prefer_localhost_replica", [0, 1])
@pytest.mark.parametrize("custom_key", ["sipHash64(key)", "key"])
@pytest.mark.parametrize("filter_type", ["default", "range"])
def test_parallel_replicas_custom_key_failover(
    start_cluster,
    use_hedged_requests,
    prefer_localhost_replica,
    custom_key,
    filter_type,
):
    for node in nodes:
        node.rotate_logs()

    cluster = "test_single_shard_multiple_replicas"
    table = "test_table"

    create_tables(cluster, table)

    expected_result = ""
    for i in range(4):
        expected_result += f"{i}\t500\n"

    log_comment = "d304e2a7-ba60-49cd-8bb7-dbb6d9b40952"
    assert (
        node1.query(
            f"SELECT key, count() FROM {table}_d GROUP BY key ORDER BY key",
            settings={
                "log_comment": log_comment,
                "prefer_localhost_replica": prefer_localhost_replica,
                "max_parallel_replicas": 4,
                "parallel_replicas_custom_key": custom_key,
                "parallel_replicas_custom_key_filter_type": filter_type,
                "use_hedged_requests": use_hedged_requests,
                # "async_socket_for_remote": 0,
                # "async_query_sending_for_remote": 0,
            },
        )
        == expected_result
    )

    for node in nodes:
        node.query("system flush logs")

    # the subqueries should be spread over available nodes
    query_id = node1.query(f"select query_id from system.query_log where current_database = currentDatabase() AND log_comment = '{log_comment}' AND type = 'QueryFinish' AND initial_query_id = query_id")
    assert(query_id != '')
    query_id = query_id[:-1]

    assert(node1.query(f"SELECT count() > 0 FROM system.query_log WHERE initial_query_id = '{query_id}' AND type ='QueryFinish' AND query_id != initial_query_id ") == '1\n')
    assert(node3.query(f"SELECT count() > 0 FROM system.query_log WHERE initial_query_id = '{query_id}' AND type ='QueryFinish' AND query_id != initial_query_id ") == '1\n')

    query_count = node1.query(f"SELECT h, count() > 0 FROM clusterAllReplicas({cluster}, system.query_log) WHERE initial_query_id = '{query_id}' AND type ='QueryFinish' AND query_id != initial_query_id group by hostname() as h settings skip_unavailable_shards=1""")
    assert(query_count == 'n1\t1\nn3\t1\n')
