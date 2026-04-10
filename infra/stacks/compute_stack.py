"""EC2 GPU instance for Kronos Trader (agent + execution on one box)."""

from constructs import Construct
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_rds as rds,
    aws_secretsmanager as sm,
    aws_elasticloadbalancingv2 as elbv2,
)


class ComputeStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        vpc: ec2.Vpc,
        db_instance: rds.DatabaseInstance,
        db_secret: rds.DatabaseSecret,
        app_secret: sm.Secret,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Security group for the GPU instance
        sg = ec2.SecurityGroup(
            self, "KtInstanceSg", vpc=vpc, allow_all_outbound=True
        )
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8001), "Dashboard")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22), "SSH")

        # Allow instance to connect to RDS
        db_instance.connections.allow_default_port_from(sg)

        # IAM role for EC2
        role = iam.Role(
            self,
            "KtInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )
        db_secret.grant_read(role)
        app_secret.grant_read(role)

        # User data: install Docker and start services
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "yum update -y",
            "yum install -y docker git",
            "systemctl enable docker && systemctl start docker",
            "usermod -aG docker ec2-user",
            # Install docker-compose
            'curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose',
            "chmod +x /usr/local/bin/docker-compose",
            # Install NVIDIA driver and container toolkit for GPU
            "yum install -y kernel-devel-$(uname -r)",
            "amazon-linux-extras install -y nvidia",
            "yum install -y nvidia-container-toolkit",
            "systemctl restart docker",
        )

        # EC2 g5.xlarge instance (1x A10G GPU, 4 vCPU, 16GB RAM)
        self.instance = ec2.Instance(
            self,
            "KtGpuInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.G5, ec2.InstanceSize.XLARGE
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_group=sg,
            role=role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        100, volume_type=ec2.EbsDeviceVolumeType.GP3
                    ),
                )
            ],
        )

        # Application Load Balancer for dashboard
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "KtAlb",
            vpc=vpc,
            internet_facing=True,
        )

        listener = alb.add_listener("KtListener", port=80)

        target = elbv2.InstanceTarget(
            instance_id=self.instance.instance_id,
            port=8001,
        )

        listener.add_targets(
            "KtTargets",
            port=8001,
            targets=[target],
            health_check=elbv2.HealthCheck(path="/api/v1/health"),
        )

        cdk.CfnOutput(self, "DashboardUrl", value=f"http://{alb.load_balancer_dns_name}")
        cdk.CfnOutput(self, "InstanceId", value=self.instance.instance_id)
