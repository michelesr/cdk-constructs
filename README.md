# CDK constructs

To be used with the AWS CDK for Python

### Core

<details>
  <summary>DomainProperties (Plain object)</summary>

A conventional way to generate DNS names

```python
from ca_cdk_constructs import DomainProperties

domain_props = DomainProperties(sub_domain="myapp", zone_domain="qa.acme.org")
domain_props.zone_domain  # qa.acme.org
domain_props.domain  # returns myapp.qa.acme.org
domain_props.ingress_domain  # returns myapp-ingress.qa.acme.org

# indicating a top level domain
domain_props = DomainProperties(sub_domain="", zone_domain="myapp.acme.org")

domain_props.zone_domain  # myapp.acme.org
domain_props.domain  # returns myapp.acme.org
domain_props.ingress_domain  # returns myapp-ingress.myapp.acme.org
```

</details>

<details>
  <summary>CrossAccountDomainDelegation</summary>

Creates delegated domains

```python
from ca_cdk_constructs import CrossAccountDomainDelegation, R53ParentZoneConfig

zone = PublicHostedZone(self, "Zone", zone_name="my-subdomain.acme.org")

# creates delegation records in for my-subdomain.acme.org in acme.org
CrossAccountDomainDelegation(
    subdomain_stack,
    "MySubdomainDnsDelegation",
    parent_zone_config=R53ParentZoneConfig(
        account_id="1234566789012",
        zone_name="acme.org",
        role_name="R53UpdateRole" # existing role in the parent zone account
    ),
    hosted_zone=zone
)

```

</details>

### Edge services

<details>
    <summary>Web Application Firewall</summary>

Deploys AWS WAF using a vendored
[AWS WAF Security Automations v3.2.0](https://github.com/awslabs/aws-waf-security-automations/tree/v3.2.0)
template, with the addition of the AWS Managed `KnownBadInputs` Rule (to protect specifically
against the `log4j` vulnerability). It also allows for the addition of any additional user-defined
custom rules, by supplying a list of one or more `CfnWebACL.RuleProperty`. TO NOTE: these may
incur additional costs, if they take the total number of `WCUs` for the WAF above `1500`.

In able to accommodate custom rules, and because of the limitations on working with imported
nested templates with the CDK, the WAF provides a fixed set of standard rules - which is NOT
parameterised in the `ProtectedCloudfront` construct. In order to vary the rules (e.g. add
more of the standard rules, override any rules to COUNT, etc) you will need to copy the
construct code to your config repo and make the amendments directly in the construct and
template(s):

`SQL injection rule` - `BLOCK`

`Cross-site scripting rule` - `BLOCK`

`Flood protection rule` - `BLOCK`. A simple rate based rule, which blocks an individual IP
address if average requests over a 5-minute period from that IP address exceed a user-supplied
`RequestThreshold` and unblocks once they fall below this threshold again. CARE!! Given
that many LCAs work from a fixed single IP address, this should not be set to too low a value.

`Reputation lists rule` - `BLOCK`

For the original WAF configuration options see the "Parameters" section in the
[original template](ca_cdk_constructs/edge_services/assets/aws-waf-security-automations.json).

Usage:

```python
from ca_cdk_constructs.edge_services.waf_stack import WafStack

WafStack(app,
        "Waf",
        # The waf **MUST** be instantiated with the rule combination here. Only the
        # flood_protection_threshold and custom_rules can be varied.
        params={
            "ActivateAWSManagedRulesParam": "yes",
            "ActivateSqlInjectionProtectionParam": "yes",
            "ActivateCrossSiteScriptingProtectionParam": "yes",
            "ActivateHttpFloodProtectionParam": "yes - AWS WAF rate based rule",
            "ActivateScannersProbesProtectionParam": "no",
            "ActivateReputationListsProtectionParam": "yes",
            "ActivateBadBotProtectionParam": "no",
            # threshold requests in 5-minute period from any single IP before that
            # IP is blocked.
            "RequestThreshold": flood_protection_threshold, # default = 100
        },
        custom_rules: <list of aws_cdk.aws_wafv2.CfnWebACL.RuleProperty]> default = [],
})

```

</details>

<details>
  <summary>ProtectedCloudfront</summary>

[protected_cloudfront](ca_cdk_constructs/edge_services/protected_cloudfront.py)

Creates a Cloudfront distribution protected by the AWS WAF. The distribution forwards a
custom header that can be requested by downstream load balancers in order to prevent traffic
from hitting them directly.

When using this library construct, the only properties of the WAF that can be specified
are any custom rules to be added on top of the WAF (list of aws_cdk.aws_wafv2.CfnWebACL.RuleProperty)

Usage:

```python
from aws_cdk import App, Stack
from aws_cdk.aws_eks import HelmChart
from ca_cdk_constructs.edge_services.protected_cloudfront import ProtectedCloudfrontStack
import json

app = App()

hosted_zone =  # create or import a hosted zone

custom_rules = # optionally specify a list of aws_cdk.aws_wafv2.CfnWebACL.RuleProperty

# creates Cloudfront protected by WAF at myapp.<hosted_zone_domain>
cdn = ProtectedCloudfrontStack(app, "ca-referrals",
                                    hosted_zone=hosted_zone,
                                    sub_domain="myapp",
                                    origin_domain="my-loadbalancer-url"
                                    custom_rules=custom_rules,
                                    flood_protection_threshold="2500" # any value >= 100
                               )

# retrieve the secret header which must be added to the load balancer in order
# to prevent users bypassing the CDN ( and the WAF )
cdn.secret_header
# or
cdn.SECRET_HEADER_NAME
# and
cdn.secret_header_value

# To add the header to e.g. Kubernetes ALB ingress use:

k8s_deployment_stack = Stack(app, "K8sDeployment")
# add the header to the ALB ingress
chart_overrides = {
    "web": {
        "ingress": {
            "annotations": {
                "alb.ingress.kubernetes.io/conditions.main": json.dumps(
                    [
                        # other config can go here
                        cdn.alb_ingress_header_config_annotation
                    ]
                )
            }
        }
    }
}

HelmChart(k8s_deployment_stack, "myapp", cluster=cluster, namespace="myapp-namespace", values=chart_overrides)
```

</details>

### Kubernetes / AWS EKS

`ca_cdk_constructs` includes a vendored cdk8s library that is compatible with the [currently supported CA Kubernetes platform version](https://citizensadvice.atlassian.net/wiki/spaces/OPS/pages/2874441735/Current+version).

You need to update the version of `ca_cdk_constructs` in your project if both of these are correct:

- your project deploys k8s resources using the vendored cdk8s library
- the CA platform was updated to a new version

To vendor the libraries for the [K8s version currently supported by the CA Kubernetes platform](https://citizensadvice.atlassian.net/wiki/spaces/OPS/pages/2874441735/Current+version):

- update the k8s / crd versions in `cdk8s.yaml`
- run `cdk8s import --output ca_cdk_constructs/eks/imports`

The library can be then used as follows:

```python
import ca_cdk_constructs.eks.imports.k8s as k8s

k8s.KubeDeployment(.....)
```

<details>
  <summary>EksClusterIntegration</summary>

Makes it possible to deploy to imported EKS clusters.

```python
from ca_cdk_constructs.eks import EksClusterIntegration

# in an existing stack
eks_integration = EksClusterIntegration(self, "EksIntegration", vpc=vpc, cluster_name="mycluster")

# for imported clusters the kubectl role must be manually added to aws-auth
# The role ARN will also be available in the K8sAuthRoleArn output
eks_integration.role
# the EKS cluster
eks_integration.cluster
```

</details>

<details>
  <summary>ExternalAwsSecretsChart</summary>

cdk8s Chart to deploy [External Secrets](https://external-secrets.io/) referencing one or more AWS SecretsManager or ParameterStore secrets.

See [the tests](./tests/eks/external_secrets/test_external_secrets_chart.py)

</details>

### Storage

<details>
  <summary>ModifyDBClusterPassword</summary>

Modifies the password of an Aurora cluster

```python
modify_cluster_password = ModifyDBClusterPassword(self, "ModifyClusterPassword", cluster_id=cluster_id, secret=db_secret)
modify_cluster_password.trigger_on_stack_create_update()
# access the udnerlaying lambda to e.g. add it to a state machine
modify_cluster_password.lambda_funct
```

</details>

<details>
  <summary>AuroraFastClone</summary>

Clones an Aurora cluster.

```python
from ca_cdk_constructs.storage.aurora_clone_refresh import AuroraCloneRefresh

source_cluster = DatabaseCluster(self, "AuroraCluster", ....) # or lookup one
vpc = source_cluster.vpc # or look it up

cluster_pg = CfnDBClusterParameterGroup(
    self,
    "DBClusterParameterGroup",
    description=f"Cluster parameter group for test clone",
    family=source_cluster.engine.parameter_group_family,
    parameters={"log_hostname": 1},
)
cluster_instance_pg = rds.CfnDBParameterGroup(
    self,
    "DBParameterGroup",
    description=f"DB parameter group for test clone instance",
    family=source_cluster.engine.parameter_group_family,
    parameters={"log_hostname": 1},
)

# periodically clone the source cluster
cloned_cluster = AuroraCloneRefresh(self, "TestClone",
                              source_cluster=source_cluster,
                              source_cluster_vpc=vpc,
                              source_cluster_master_username=username,
                              db_instance_class="db.t3.medium",
                              cluster_parameter_group=cluster_pg,
                              instance_parameter_group=cluster_instance_pg,
                                    tags={
                                        "Tag": "Value"
                                    },
                              clone_schedule=Schedule.cron(minute="0", hour="8"),
                              notifications_topic=topic)

# allow access to the clone from certain ranges
cloned_cluster.allow_from(ec2.Peer.ipv4(vpc.vpc_cidr_block))
# or
clone.cluster_sg.allow_....

# access the cloned cluster credentials
cloned_cluster.clone_secret # DatabaseSecret
# the clone SNS topic
cloned_cluster.notifications_topic # Topic

# the event rule
cloned_cluster.event_rule

```

</details>

## Tests

```shell
poetry install

poetry run pytest
```
