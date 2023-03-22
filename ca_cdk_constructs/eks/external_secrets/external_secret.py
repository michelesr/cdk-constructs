from attr import Factory, define, ib

from typing import Union, Any
from cdk8s import ApiObjectMetadata
from constructs import Construct

from ca_cdk_constructs.eks.imports.io.external_secrets import (
    ExternalSecretV1Beta1,
    ExternalSecretV1Beta1Spec,
    ExternalSecretV1Beta1SpecSecretStoreRef,
    ExternalSecretV1Beta1SpecDataRemoteRef,
    ExternalSecretV1Beta1SpecTarget,
    ExternalSecretV1Beta1SpecData,
)


@define
class ExternalSecretSource:
    """
    Container for secret references to be used by :class:`~ExternalSecret~`

        ExternalSecretSource(
            source_secret="secret-1", # e.g AWS Secrets manager secret name
            k8s_secret_name="app-secret2",
            refresh_interval = "1h", # default
            secret_mappings={
                "some_key": "KEY_IN_K8S_SECRET",
                "some_key.subkey": "FOO",
            }
        ),
        )
    """

    source_secret: str
    k8s_secret_name: str
    secret_mappings: dict[str, str]
    refresh_interval: str = "1h"


class ExternalSecret(Construct):
    """
    io.external_secrets.ExternalSecret facade which:
        - requires existing external secret stores, possibly created by a different workflow as explained in https://external-secrets.io/v0.6.1/overview/#roles-and-responsibilities
        - provides a simpler interface for creating known, supported external secrets configurations, e.g. it does not support custom [templating](https://external-secrets.io/v0.7.0-rc1/guides/templating/)
        - always uses an ExternalSecret API version that is compatible and supported in CA - managed clusters.

    Usage:

        ExternalSecret(
            self,
            "dbSecret",
            store_name = "secrets-manager",
            secret_source=ExternalSecretSource(
                source_secret="secret-1", # AWS Secrets manager secret name
                k8s_secret_name="app-secret2", # defaults to dns compliant name derived from source_secret
                refresh_interval = "1h", # default
                secret_mappings={
                    "KEY_IN_SECRET": "KEY_IN_K8S_SECRET",
                    "KEY_IN_SECRET.SUBKEY": "KEY_IN_K8S_SECRET", # lookup nested secret values
                }
            ),
            metadata={
                "name": "app-secret", # if a name for the ExternalSecret is not provided, it will be autogenerated by CDK
                "annotations": {"hello": "world"},
                "labels": {"foo": "bar"}
            }
        )
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        store_name: str,
        secret_source: ExternalSecretSource,
        metadata: Union[dict[str, Any], ApiObjectMetadata] = {},
    ):
        super().__init__(scope, id)
        self._k8s_secret_name = secret_source.k8s_secret_name

        ExternalSecretV1Beta1(
            self,
            "Resource",
            metadata=metadata,
            spec=ExternalSecretV1Beta1Spec(
                secret_store_ref=ExternalSecretV1Beta1SpecSecretStoreRef(
                    name=store_name,
                    kind="SecretStore",
                ),
                refresh_interval=secret_source.refresh_interval,
                target=ExternalSecretV1Beta1SpecTarget(name=secret_source.k8s_secret_name),
                data=[
                    ExternalSecretV1Beta1SpecData(
                        remote_ref=ExternalSecretV1Beta1SpecDataRemoteRef(
                            key=secret_source.source_secret,
                            # which property to retrieve from provider
                            property=k,
                        ),
                        secret_key=v  # the key in the K8s secret e.g. the env var name
                        or str(k).split(".")[-1],
                        # if not specified, set the secret key = the last element of the pottentially . separated provider key
                    )
                    for k, v in secret_source.secret_mappings.items()
                ],
            ),
        )

    @property
    def k8s_secret_name(self) -> str:
        return self._k8s_secret_name
