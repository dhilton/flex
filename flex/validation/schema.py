import itertools
import collections
import functools

import six

from django.core.exceptions import ValidationError

from flex.exceptions import SafeNestedValidationError
from flex.constants import (
    OBJECT,
    EMPTY,
)
from flex.decorators import skip_if_not_of_type
from flex.validation.common import (
    skip_if_empty,
    generate_type_validator,
    generate_format_validator,
    generate_required_validator,
    generate_multiple_of_validator,
    generate_minimum_validator,
    generate_maximum_validator,
    generate_min_length_validator,
    generate_max_length_validator,
    generate_min_items_validator,
    generate_max_items_validator,
    generate_unique_items_validator,
    generate_pattern_validator,
    generate_enum_validator,
    validate_object,
)


@skip_if_empty
@skip_if_not_of_type(OBJECT)
def validate_min_properties(value, minimum):
    if len(value.keys()) < minimum:
        raise ValidationError(
            "Object must have more than {0} properties.  It had {1}".format(
                minimum, len(value.keys()),
            ),
        )


def generate_min_properties_validator(minProperties, **kwargs):
    return functools.partial(validate_min_properties, minimum=minProperties)


@skip_if_empty
@skip_if_not_of_type(OBJECT)
def validate_max_properties(value, maximum):
    if len(value.keys()) > maximum:
        raise ValidationError(
            "Object must have less than {0} properties.  It had {1}".format(
                maximum, len(value.keys()),
            ),
        )


def generate_max_properties_validator(maxProperties, **kwargs):
    return functools.partial(validate_max_properties, maximum=maxProperties)


def construct_items_validators(items, context):
    if isinstance(items, collections.Mapping):
        items_validators = construct_schema_validators(
            items,
            context,
        )
    elif isinstance(items, six.string_types):
        items_validators = {
            '$ref': LazyReferenceValidator(items, context),
        }
    else:
        assert 'Should not be possible'
    return items_validators


def validate_items(objs, validators):
    errors = []
    for obj, validator in zip(objs, validators):
        try:
            validate_object(obj, validator, inner=True)
        except ValidationError as e:
            errors.extend(list(e.messages))

    if errors:
        raise SafeNestedValidationError(errors)


def generate_items_validator(items, context, **kwargs):
    if isinstance(items, collections.Mapping) or isinstance(items, six.string_types):
        # If items is a reference or a schema, we pass it through as an
        # ever repeating list of the same validation dictionary, thus
        # validating all of the objects against the same schema.
        items_validators = itertools.repeat(construct_items_validators(
            items,
            context,
        ))
    elif isinstance(items, collections.Sequence):
        # We generate a list of validator dictionaries and then chain it
        # with an empty schema that repeats forever.  This ensures that if
        # the array of objects to be validated is longer than the array of
        # validators, then the extra elements will always validate since
        # they will be validated against an empty schema.
        items_validators = itertools.chain(
            map(functools.partial(construct_items_validators, context=context), items),
            itertools.repeat({}),
        )
    else:
        assert "Should not be possible"
    return functools.partial(
        validate_items, validators=items_validators,
    )


validator_mapping = {
    'type': generate_type_validator,
    'multipleOf': generate_multiple_of_validator,
    'minimum': generate_minimum_validator,
    'maximum': generate_maximum_validator,
    'minLength': generate_min_length_validator,
    'maxLength': generate_max_length_validator,
    'minItems': generate_min_items_validator,
    'maxItems': generate_max_items_validator,
    'uniqueItems': generate_unique_items_validator,
    'enum': generate_enum_validator,
    'minProperties': generate_min_properties_validator,
    'maxProperties': generate_max_properties_validator,
    'pattern': generate_pattern_validator,
    'format': generate_format_validator,
    'required': generate_required_validator,
    'items': generate_items_validator,
}


def validate_properties(obj, key, validators):
    if obj is EMPTY:
        return
    validate_object(obj.get(key, EMPTY), validators, inner=True)


class LazyReferenceValidator(object):
    """
    This class acts as a lazy validator for references in schemas to prevent an
    infinite recursion error when a schema references itself, or there is a
    reference loop between more than one schema.

    The validator is only constructed if validator is needed.
    """
    def __init__(self, reference, context):
        # TODO: something better than this assertion
        assert 'definitions' in context
        assert reference in context['definitions']
        self.reference = reference
        self.context = context

    def __call__(self, value):
        return validate_object(value, self.validators, inner=True)

    @property
    def validators(self):
        return construct_schema_validators(
            self.context['definitions'][self.reference],
            self.context,
        )

    def items(self):
        return self.validators.items()


def construct_schema_validators(schema, context):
    """
    Given a schema object, construct a dictionary of validators needed to
    validate a response matching the given schema.

    Special Cases:
        - $ref:
            These validators need to be Lazily evaluating so that circular
            validation dependencies do not result in an infinitely deep
            validation chain.
        - properties:
            These validators are meant to apply to properties of the object
            being validated rather than the object itself.  In this case, we
            need recurse back into this function to generate a dictionary of
            validators for the property.
    """
    validators = {}
    if '$ref' in schema:
        validators['$ref'] = LazyReferenceValidator(
            schema['$ref'],
            context,
        )
    if 'properties' in schema:
        # I don't know why this set intersection is enforced...?  Why did I do this.
        intersection = set(schema['properties'].keys()).intersection(schema.keys())
        assert not intersection

        for property_, property_schema in schema['properties'].items():
            property_validators = construct_schema_validators(
                property_schema,
                context,
            )
            validators[property_] = functools.partial(
                validate_properties,
                key=property_,
                validators=property_validators,
            )
    assert 'context' not in schema
    for key in schema:
        if key in validator_mapping:
            validators[key] = validator_mapping[key](context=context, **schema)
    return validators
