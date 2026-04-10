#!/usr/bin/env python3
"""Kronos Trader CDK application."""

import aws_cdk as cdk

from stacks.network_stack import NetworkStack
from stacks.data_stack import DataStack
from stacks.compute_stack import ComputeStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1",
)

network = NetworkStack(app, "KtNetwork", env=env)
data = DataStack(app, "KtData", vpc=network.vpc, env=env)
ComputeStack(
    app,
    "KtCompute",
    vpc=network.vpc,
    db_instance=data.db_instance,
    db_secret=data.db_secret,
    app_secret=data.app_secret,
    env=env,
)

app.synth()
