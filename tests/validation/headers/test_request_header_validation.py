import pytest

from flex.serializers.core import (
    HeaderSerializer,
)
from flex.constants import (
    INTEGER,
)
from flex.validation.common import (
    validate_object,
)
from flex.validation.header import (
    construct_header_validators
)
from flex.error_messages import MESSAGES

from tests.utils import assert_error_message_equal


@pytest.mark.parametrize(
    'type_,value',
    (
        (INTEGER, '1'),
    )
)
def test_header_type_validation_for_invalid_values(type_, value):
    from django.core.exceptions import ValidationError
    serializer = HeaderSerializer(
        data={
            'type': type_,
        }
    )
    assert serializer.is_valid()
    header_definition = serializer.object
    validators = construct_header_validators(header_definition=header_definition, context={})

    with pytest.raises(ValidationError) as err:
        validate_object(value, validators, inner=True)

    assert 'type' in err.value.messages[0]
    assert_error_message_equal(
        err.value.messages[0]['type'][0],
        MESSAGES['type']['invalid'],
    )
