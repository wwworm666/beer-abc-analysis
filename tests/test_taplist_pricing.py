"""Price provenance, current orders, portions, departments and source media."""
from copy import deepcopy
import unittest

from core.taplist_pricing import enrich_prices, DRAFT_GROUP_ID
from scripts.enrich_untappd_media import parse_media


def sources(keg='keg'):
    return {'date': '2026-09-20', 'checked_at': '2026-09-20T12:00:00+03:00',
        'groups': '<groupDtoes><groupDto><name>Большой пр. В.О</name><departmentId>dep</departmentId>'
                  '<restaurantSectionInfos><restaurantSectionInfo><id>section</id></restaurantSectionInfo>'
                  '</restaurantSectionInfos></groupDto></groupDtoes>',
        'product_groups': [{'id': DRAFT_GROUP_ID, 'parent': None}],
        'products': [{'id': 'dish', 'type': 'DISH', 'parent': DRAFT_GROUP_ID, 'name': 'Совсем другое имя (0,5)',
                      'defaultSalePrice': 100, 'defaultIncludedInMenu': True, 'unitCapacity': 0.5}],
        'charts': [{'id': 'recipe', 'assembledProductId': 'dish', 'dateFrom': '2026-01-01',
                    'effectiveDirectWriteoffStoreSpecification': {'departments': [], 'inverse': False},
                    'productSizeAssemblyStrategy': 'COMMON', 'items': [{'productId': keg, 'amount': 0.55}]}],
        'prices': [{'departmentId': 'dep', 'productId': 'dish', 'productSizeId': None,
                    'prices': [{'dateFrom': '2026-09-01', 'dateTo': '2026-10-01', 'price': '490.50',
                                'included': True, 'documentId': 'order', 'schedule': None,
                                'pricesForCategories': [{'categoryId': 'special', 'price': 1}]}]}],
        'scales': {}}


class TaplistPriceTests(unittest.TestCase):
    def setUp(self):
        self.data = sources()

    def row(self, bar='bar1'):
        return enrich_prices([{'bar_id': bar, 'iiko_product_id': 'keg'}],
                             {'products': {'keg': {}}}, self.data)[0]

    def test_current_regular_price_exact_guid_and_sale_volume_not_recipe_loss(self):
        row = self.row()
        serving = row['servings'][0]
        self.assertEqual(serving['price_rub'], '490.50')
        self.assertEqual(serving['portion_liters'], '0.5')
        self.assertEqual(serving['price_source']['document_id'], 'order')
        self.assertEqual(row['price_status'], 'verified')

    def test_removed_item_does_not_fall_back_to_default_price(self):
        self.data['prices'][0]['prices'][0]['included'] = False
        self.assertEqual(self.row()['servings'], [])

    def test_default_price_only_when_no_current_order_and_included(self):
        self.data['prices'][0]['prices'][0]['dateTo'] = '2026-09-20'
        self.assertEqual(self.row()['servings'][0]['price_rub'], '100.00')
        self.data['products'][0]['defaultIncludedInMenu'] = False
        self.assertEqual(self.row()['servings'], [])

    def test_future_price_ignored(self):
        self.data['prices'][0]['prices'].append({'dateFrom': '2026-09-21', 'price': 900, 'included': True})
        self.assertEqual(self.row()['servings'][0]['price_rub'], '490.50')

    def test_overlapping_or_scheduled_price_not_presented_as_exact(self):
        self.data['prices'][0]['prices'].append(deepcopy(self.data['prices'][0]['prices'][0]))
        self.assertEqual(self.row()['servings'], [])
        self.data['prices'][0]['prices'].pop()
        self.data['prices'][0]['prices'][0]['schedule'] = {'time': '18:00'}
        self.assertEqual(self.row()['servings'], [])

    def test_open_price_and_sub_kopeck_price_rejected(self):
        self.data['products'][0]['canSetOpenPrice'] = True
        self.assertEqual(self.row()['servings'], [])
        self.data['products'][0]['canSetOpenPrice'] = False
        self.data['prices'][0]['prices'][0]['price'] = '100.001'
        self.assertEqual(self.row()['servings'], [])

    def test_explicit_zero_order_is_not_missing(self):
        self.data['prices'][0]['prices'][0]['price'] = 0
        self.assertEqual(self.row()['servings'][0]['price_rub'], '0.00')

    def test_missing_volume_does_not_become_keg_amount(self):
        self.data['products'][0].update(name='Без объёма', unitCapacity=0)
        self.assertEqual(self.row()['servings'], [])

    def test_food_with_beer_ingredient_is_not_a_sale_portion(self):
        self.data['products'][0]['parent'] = 'kitchen'
        self.assertEqual(self.row()['servings'], [])

    def test_unknown_bar_and_other_department_do_not_cross_match(self):
        self.assertEqual(self.row('bar2')['servings'], [])
        self.data['prices'][0]['departmentId'] = 'elsewhere'
        self.data['products'][0]['defaultSalePrice'] = 0
        self.assertEqual(self.row()['servings'], [])

    def test_recipe_department_filter_and_excluded_section(self):
        self.data['charts'][0]['items'][0]['storeSpecification'] = {'departments': ['elsewhere'], 'inverse': False}
        self.assertEqual(self.row()['servings'], [])
        self.data['charts'][0]['items'][0]['storeSpecification']['inverse'] = True
        self.assertEqual(len(self.row()['servings']), 1)
        self.data['products'][0]['excludedSections'] = ['section']
        self.assertEqual(self.row()['servings'], [])

    def test_direct_writeoff_and_deleted_dish_not_matched(self):
        self.data['charts'][0]['effectiveDirectWriteoffStoreSpecification']['inverse'] = True
        self.assertEqual(self.row()['servings'], [])
        self.data['charts'][0]['effectiveDirectWriteoffStoreSpecification']['inverse'] = False
        self.data['products'][0]['deleted'] = True
        self.assertEqual(self.row()['servings'], [])

    def test_latest_recipe_only_and_no_name_fallback(self):
        new = deepcopy(self.data['charts'][0])
        new.update(id='new', dateFrom='2026-09-10', items=[{'productId': 'another-keg', 'amount': 0.5}])
        self.data['charts'].append(new)
        self.assertEqual(self.row()['servings'], [])

    def test_multiple_portions_keep_distinct_exact_prices(self):
        product = deepcopy(self.data['products'][0]); product.update(id='small', name='Малая (0,25)')
        chart = deepcopy(self.data['charts'][0]); chart.update(id='small-recipe', assembledProductId='small')
        price = deepcopy(self.data['prices'][0]); price.update(productId='small'); price['prices'][0]['price'] = 270
        self.data['products'].append(product); self.data['charts'].append(chart); self.data['prices'].append(price)
        self.assertEqual([(s['portion_liters'], s['price_rub']) for s in self.row()['servings']],
                         [('0.25', '270.00'), ('0.5', '490.50')])

    def test_specific_size_recipe_and_takeaway_size(self):
        self.data['products'][0].update(productScaleId='scale', name='Без размера')
        self.data['scales']['dish'] = {'productSizes': [{'id': 'size', 'name': '0,5 (б)'}]}
        self.data['prices'][0]['productSizeId'] = 'size'
        self.data['charts'][0]['productSizeAssemblyStrategy'] = 'SPECIFIC'
        self.data['charts'][0]['items'][0]['productSizeSpecification'] = 'other'
        self.assertEqual(self.row()['servings'], [])
        self.data['charts'][0]['items'][0]['productSizeSpecification'] = 'size'
        self.assertEqual(self.row()['servings'][0]['portion_liters'], '0.5')
        self.data['scales']['dish']['productSizes'][0]['disabled'] = True
        self.assertEqual(self.row()['servings'], [])


class TaplistMediaTests(unittest.TestCase):
    def html(self, description='Настоящее описание'):
        return ('<link rel="canonical" href="https://untappd.com/b/beer/123">'
                '<a class="label image-big" data-image="https://assets.untappd.com/site/beer_logos/beer-Old_123.jpeg"></a>'
                '<div class="beer-descrption-read-less">' + description + '<a>Show Less</a></div>'
                '<a class="label" href="related"></a>')

    def test_primary_label_and_description_without_interface_text(self):
        result = parse_media(self.html(), '123')
        self.assertEqual(result['description'], 'Настоящее описание')
        self.assertTrue(result['photo_url'].endswith('beer-Old_123.jpeg'))

    def test_different_canonical_beer_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_media(self.html(), '456')

    def test_excerpt_is_bounded_and_preserves_escaped_text(self):
        result = parse_media(self.html(' &amp; '.join(['слово'] * 40)), '123')
        self.assertLessEqual(len(result['description'].split()), 25)
        self.assertTrue(result['description_is_excerpt'])
        self.assertNotIn('&amp;', result['description'])

    def test_brewery_logo_is_not_a_beer_photo(self):
        html = self.html().replace('beer_logos/beer-Old_123.jpeg', 'brewery_logos/brewery-1.jpeg')
        self.assertIsNone(parse_media(html, '123')['photo_url'])

    def test_observed_community_photo_used_when_label_missing(self):
        html = self.html().replace('beer_logos/beer-Old_123.jpeg', 'brewery_logos/brewery-1.jpeg')
        src = 'https://images.untp.beer/crop?width=640&amp;url=https://untappd.s3.amazonaws.com/photos/2026_09_20/real.jpg'
        result = parse_media(html + '<img alt="Check-in Photo" src="' + src + '">', '123')
        self.assertEqual(result['photo_kind'], 'community_photo')
        self.assertIn('real.jpg', result['photo_url'])


if __name__ == '__main__':
    unittest.main()
