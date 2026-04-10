"""RDS PostgreSQL and Secrets Manager for Kronos Trader."""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2, aws_rds as rds, aws_secretsmanager as sm


class DataStack(cdk.Stack):
    def __init__(
        self, scope: Construct, id: str, vpc: ec2.Vpc, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Database credentials
        self.db_secret = rds.DatabaseSecret(
            self, "KtDbSecret", username="kt"
        )

        # PostgreSQL instance
        self.db_instance = rds.DatabaseInstance(
            self,
            "KtDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            credentials=rds.Credentials.from_secret(self.db_secret),
            database_name="kt_execution",
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,
            deletion_protection=True,
        )

        # Application secrets (Alpaca keys, auth tokens)
        self.app_secret = sm.Secret(
            self,
            "KtAppSecrets",
            secret_name="kt/app-secrets",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"alpaca_api_key":"","alpaca_secret_key":"","exec_auth_token":"","agent_auth_token":""}',
                generate_string_key="exec_auth_token",
            ),
        )

        # Export values so compute stack can reference without creating cyclic deps
        cdk.CfnOutput(self, "DbEndpoint", value=self.db_instance.db_instance_endpoint_address)
        cdk.CfnOutput(self, "DbPort", value=self.db_instance.db_instance_endpoint_port)
        cdk.CfnOutput(self, "DbSecretArn", value=self.db_secret.secret_arn)
        cdk.CfnOutput(self, "AppSecretArn", value=self.app_secret.secret_arn)
