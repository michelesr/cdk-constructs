from aws_cdk import (CfnOutput, Duration, Environment, PhysicalName,
                     RemovalPolicy, Stack)
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as r53
from aws_cdk import aws_route53_targets as r53_targets
from aws_cdk import aws_s3 as s3
from cdk_remote_stack import RemoteOutputs
from constructs import Construct

from cdk_constructs.waf import WafStack


class ProtectedCloudfrontStack(Stack):
    # A WAF protected cloudfront that also sets a "secret" header that can be checked by upstream load balancers to prevent requests bypassing cloudfront

    SECRET_HEADER_NAME = "X-Secret-CF-ALB-Header"

    def __init__(self, scope: Construct, construct_id: str, hosted_zone: r53.HostedZone, domain: str, origin_domain: str, env_context: dict,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.context = env_context
        self.env_name = self.context['env_name']

        # waf and the cloudfront log bucket must be deployed to us-east-1
        us_east_environment = Environment(region="us-east-1")

        # cloudfront log bucket
        access_logs_bucket = s3.Bucket(
            self,
            "CloudfrontLogBucket",
            bucket_name=PhysicalName.GENERATE_IF_NEEDED,
            removal_policy=RemovalPolicy.DESTROY,
            lifecycle_rules=[s3.LifecycleRule(enabled=True, expiration=Duration.days(31 * 6))])

        # the waf automations solution stack deployed from the template in the assets/ folder
        waf = WafStack(
            self,
            "WafStack",
            log_requests=False,  # todo
            params={
                "ActivateAWSManagedRulesParam": "True",
                "ActivateSqlInjectionProtectionParam": "True",
                "ActivateCrossSiteScriptingProtectionParam": "True",
                "ActivateHttpFloodProtectionParam": "True",
                "ActivateScannersProbesProtectionParam": "True",
                "ActivateReputationListsProtectionParam": "True",
                "ActivateBadBotProtectionParam": "False",
                "AppAccessLogBucket": access_logs_bucket.bucket_name
            },
            env=us_east_environment)

        # need to get the web acl but can't pass it directly:
        #   "Stack "qaCaReferrals/cloudfront" cannot consume a cross reference from stack "qaCaReferrals/cloudfront/WafStack.
        #   Cross stack references are only supported for stacks deployed to the same environment or between nested stacks and their parent stack"
        # so this is a workaround - the waf template outputs (in us-east-1) are retrieved by a lambda in eu-west-1
        # RemoteOutputs is provided by the cdk-remote-stack library
        waf_outputs = RemoteOutputs(self, "Outputs", stack=waf)

        self.secret_header = f"{self.env_name}-{self.stack_name}"

        certificate = acm.DnsValidatedCertificate(self,
                                                  "CloudfrontCertificate",
                                                  domain_name=domain,
                                                  region="us-east-1",
                                                  hosted_zone=hosted_zone)
        http_origin = origins.HttpOrigin(domain_name=origin_domain,
                                         custom_headers=self.secretHeader())

        assets_origin_request_policy = cloudfront.OriginRequestPolicy(
                self,
                "StaticAssetsOriginRequestPolicy",
                comment="Forward the Host header for assets",
                header_behavior=cloudfront.OriginRequestHeaderBehavior.allow_list("Host"),
                cookie_behavior=cloudfront.OriginRequestCookieBehavior.none(),
                query_string_behavior=cloudfront.OriginRequestQueryStringBehavior.none())

        cdn = cloudfront.Distribution(
            self,
            "CdnDistribution",
            domain_names=[domain],
            enable_logging=True,
            log_bucket=access_logs_bucket,
            certificate=certificate,
            web_acl_id=waf_outputs.get("WAFWebACLArn"),
            comment=f"CDN for {self.stack_name}",
            geo_restriction=cloudfront.GeoRestriction.allowlist("GB", "JE", "GG"),  # UK, Jersey and Guernsey
            default_behavior=cloudfront.BehaviorOptions(
                origin=http_origin,
                compress=True,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS))

        cdn.add_behavior(path_pattern="/assets/*",
                         origin=http_origin,
                         compress=True,
                         allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                         cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                         cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                         origin_request_policy=assets_origin_request_policy,
                         viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS)

        cdn.node.add_dependency(waf)

        self._cdn = cdn

        CfnOutput(self, "CloudfrontDistributionId", value=cdn.distribution_id)
        CfnOutput(self, "CloudfrontDistributionDomain", value=cdn.distribution_domain_name)
        CfnOutput(self, "SecretHeaderArn", value=self.secret_header)

        domain_prefix = domain.split('.')[0]
        alias = r53_targets.CloudFrontTarget(cdn)
        r53.ARecord(self,
                    "CloudfrontDNS",
                    zone=hosted_zone,
                    record_name=domain_prefix,
                    target=r53.RecordTarget.from_alias(alias))

    def cdn(self) -> cloudfront.Distribution:
        # direct access to the Cloudfront dsistribution resource
        return self._cdn

    def secretHeaderValue(self) -> str:
        return self.secret_header

    def secretHeader(self) -> dict:
        return {self.SECRET_HEADER_NAME: self.secret_header}
