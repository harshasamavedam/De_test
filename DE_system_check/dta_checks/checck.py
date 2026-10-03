import subprocess


def data_run(script):
    result = subprocess.run(
        ["docker", "exec", "payments-orders-cassandra", "cqlsh", "-e",
         script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


categories = ("electronics", "clothing", "other")

for category in categories:
    output = data_run(
        "SELECT product_id, variant_id "
        f"FROM payments.product_item WHERE category = '{category}'"
    )
    product_ids = set()
    variants = set()

    for line in output.splitlines():
        if "|" not in line:
            continue
        product_id, variant_id = (value.strip() for value in line.split("|", 1))
        if product_id == "product_id" or set(product_id) <= {"-", "+"}:
            continue
        product_ids.add(product_id)
        variants.add((product_id, variant_id))

    print(
        f"{category}: {len(product_ids)} products, "
        f"{len(variants)} variants"
    )