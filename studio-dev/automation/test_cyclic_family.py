import unittest
from cyclic_family import observed_family


class ObservedFamilyTest(unittest.TestCase):
    def test_color_only_does_not_invent_size(self):
        result = observed_family({'dimensions': [['color_name']], 'variationValues': [{'color_name': ['Black', 'Red']}], 'dimensionValuesDisplayData': [{'A': ['Black'], 'B': ['Red']}]})
        self.assertEqual(result['sizes'], [])
        self.assertFalse(result['size_dimension_present'])
        self.assertEqual(result['variants'], [{'asin': 'A', 'color': 'Black', 'size': ''}, {'asin': 'B', 'color': 'Red', 'size': ''}])

    def test_sparse_mapping_does_not_make_cartesian_product(self):
        result = observed_family({'dimensions': [['size_name', 'color_name']], 'variationValues': [{'size_name': ['S', 'M'], 'color_name': ['Black', 'Red']}], 'dimensionValuesDisplayData': [{'A': ['S', 'Black'], 'B': ['M', 'Red']}]})
        self.assertEqual(len(result['variants']), 2)
        self.assertTrue(result['size_dimension_present'])

    def test_reverse_dimension_order(self):
        result = observed_family({'dimensions': [['color_name', 'size_name']], 'variationValues': [{'size_name': ['M'], 'color_name': ['Red']}], 'dimensionValuesDisplayData': [{'A': ['Red', 'M']}]})
        self.assertEqual(result['variants'][0], {'asin': 'A', 'color': 'Red', 'size': 'M'})

    def test_missing_child_attribute_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_family({'dimensions': [['size_name', 'color_name']], 'variationValues': [{'size_name': ['S'], 'color_name': ['Black']}], 'dimensionValuesDisplayData': [{'A': ['Black']}]})
